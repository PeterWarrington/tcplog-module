#include <linux/module.h>
#include <linux/printk.h>
#include <net/tcp.h>
#include <linux/inet_diag.h>
#include <linux/inet.h>
#include <linux/string.h>
#include <linux/ktime.h>
#include <linux/spinlock.h>

#include "tcplog.h"

// Comments from net/tcp.h
static char *log_ca_events[] = {
    "CA_EVENT_TX_START",    /* first transmit when no packets in flight */
    "CA_EVENT_CWND_RESTART",    /* congestion window restart */
    "CA_EVENT_COMPLETE_CWR",    /* end of congestion recovery */
    "CA_EVENT_LOSS",        /* loss timeout */
    "CA_EVENT_ECN_NO_CE",    /* ECT set, but not CE marked */
    "CA_EVENT_ECN_IS_CE",    /* received CE marked IP packet */
};

// Comments from linux/tools/include/uapi/linux/tcp.h
static char* log_ca_states[] = {
    "TCP_CA_Open",      /* Nothing bad has been observed recently. No apparent reordering, packet loss, or ECN marks. */
    "TCP_CA_Disorder",  /* The sender enters disordered state when it has received DUPACKs or SACKs in the last round of packets sent. This could be due to packet loss or reordering but needs further information to confirm packets have been lost. */
    "TCP_CA_CWR",       /* The sender enters Congestion Window Reduction (CWR) state when it has received ACKs with ECN-ECE marks, or has experienced congestion or packet discard on the sender host (e.g. qdisc). */
    "TCP_CA_Recovery",  /* The sender is in fast recovery and retransmitting lost packets, typically triggered by ACK events. */
    "TCP_CA_Loss",      /* The sender is in loss recovery triggered by retransmission timeout. */
};

static char event_template[] = "{\n"
    "\t\"time\": $TIME,\n"
    "\t\"name\": \"$NAME\",\n"
    "\t\"data\": {\n"
    "\t\t\"source_port\": \"$SPRT\",\n"
    "\t\t\"destination_port\": \"$DPRT\",\n"
    "\t\t\"state\": \"$STAT\",\n"
    "\t\t\"state_variables\": {\n"
    "\t\t\t\"cwnd\": $CWND,\n"
    "\t\t\t\"iw\": $IWND,\n"
    "\t\t\t\"rwnd\": $RWND,\n"
    "\t\t\t\"ssthresh\": $STHR,\n"
    "\t\t\t\"prior_cwnd\": $PWND,\n"
    "\t\t\t\"prr_delivered\": $PDLV,\n"
    "\t\t\t\"prr_out\": $POUT,\n"
    "\t\t},\n"
    "\t$DATA\n"
    "\t}\n"
    "}\n";

#define DMESG_VERBOSE 0
#define DMESG_LOG 1

#define TEMPLATE_TOKEN_SIZE 5

// For Character Device logging
#define DEVICE_NAME "tcplog"
#define LOG_BUF_ENTRY_SIZE 2048
#define LOG_BUF_ENTRY_COUNT_MAX 32

static spinlock_t tcplog_lock;
static DECLARE_WAIT_QUEUE_HEAD(tcplog_wq);
static char tcplog_buffer[LOG_BUF_ENTRY_COUNT_MAX][LOG_BUF_ENTRY_SIZE];
static int tcplog_write_index = 0;
static int tcplog_read_index = 0;
static int tcplog_entry_count = 0;
static int tcplog_last_read_index = 0;
static int tcplog_entry_len[LOG_BUF_ENTRY_COUNT_MAX];
static bool tcplog_buf_read_ready = false;
static u64 tcplog_last_read_time = 0;
static int tcplog_dev_semaphore = 0;
static struct file_operations tcplog_device_ops = {
  .read = tcplog_device_read,
  .write = tcplog_device_write,
  .open = tcplog_device_open,
  .release = tcplog_device_release
};

void tcplog_log(const char *msg)
{
    if (DMESG_LOG)
        printk("%s", msg);
        
    spin_lock_bh(&tcplog_lock);
    int msg_len = strlen(msg);

    if (msg_len >= LOG_BUF_ENTRY_SIZE) {
        msg_len = LOG_BUF_ENTRY_SIZE - 1;
    }
    tcplog_buffer[tcplog_write_index][msg_len] = '\0';

    memcpy(tcplog_buffer[tcplog_write_index], msg, msg_len);
    tcplog_entry_len[tcplog_write_index] = msg_len;

    tcplog_write_index = (tcplog_write_index + 1) % LOG_BUF_ENTRY_COUNT_MAX;
    if (tcplog_write_index == tcplog_read_index)
        tcplog_read_index = (tcplog_read_index + 1) % LOG_BUF_ENTRY_COUNT_MAX;
    
    tcplog_entry_count = min(tcplog_entry_count + 1, 8);

    // If we have filled entries or 50 miliseconds have passed, then flush them to readers
    u64 current_time = ktime_get_ns();
    u64 time_since_last_read = current_time - tcplog_last_read_time;
    if (tcplog_read_index == tcplog_last_read_index || time_since_last_read > 50 * 1000) {
        tcplog_last_read_index = tcplog_read_index;

        if (DMESG_VERBOSE)
            printk("DEV_TCPLOG: READY");
        tcplog_buf_read_ready = true;
        tcplog_last_read_time = current_time;
        spin_unlock_bh(&tcplog_lock);
        // wake any readers waiting for new data 
        wake_up_interruptible(&tcplog_wq);
    } else {
        if (DMESG_VERBOSE)
            printk("DEV_TCPLOG: NOT READY");
        tcplog_buf_read_ready = false;
        spin_unlock_bh(&tcplog_lock);
    }
}

void tcplog_log_event(char* event_name, struct sock *sk, struct tcplog_extra_data *extra) {
    char *local_buffer = kmalloc(LOG_BUF_ENTRY_SIZE, GFP_ATOMIC);
    int buf_i = 0;

    char token_buffer[TEMPLATE_TOKEN_SIZE] = "\0";
    int token_i = 0;
    bool in_token = false;

    int template_i = 0;
    char template_c = '\0';
    do {
        template_c = event_template[template_i++];
        if (DMESG_VERBOSE)
            printk("DEV_TCPLOG: tcplog_log_event - token_buffer=%s, template_c='%c', in_token=%d\n", token_buffer, template_c, in_token);
        if ((template_c == '$' || in_token) && token_i < TEMPLATE_TOKEN_SIZE) {
            in_token = true;
            token_buffer[token_i++] = template_c;
        } else {
            token_buffer[token_i++] = '\0';
            if (in_token) {
                // token_buffer should have token
                in_token = false;
                if (strcmp(token_buffer, "$NAME") == 0) {
                    for (int i=0; event_name[i] != '\0'; i++) local_buffer[buf_i++] = event_name[i];
                } else if (strcmp(token_buffer, "$CWND") == 0) {
                    u32 cwnd = log_get_cwnd(sk);
                    char var_buf[16] = "\0";
                    sprintf(var_buf, "%d", cwnd);
                    for (int i=0; var_buf[i] != '\0'; i++) local_buffer[buf_i++] = var_buf[i];
                } else if (strcmp(token_buffer, "$IWND") == 0) {
                    u32 iw = log_get_initial_wnd(sk);
                    char var_buf[16] = "\0";
                    sprintf(var_buf, "%d", iw);
                    for (int i=0; var_buf[i] != '\0'; i++) local_buffer[buf_i++] = var_buf[i];
                } else if (strcmp(token_buffer, "$RWND") == 0) {
                    u32 rw = log_get_recv_wnd(sk);
                    char var_buf[16] = "\0";
                    sprintf(var_buf, "%d", rw);
                    for (int i=0; var_buf[i] != '\0'; i++) local_buffer[buf_i++] = var_buf[i];
                } else if (strcmp(token_buffer, "$STHR") == 0) {
                    u32 ssthresh = log_get_ssthresh(sk);
                    char var_buf[16] = "\0";
                    sprintf(var_buf, "%d", ssthresh);
                    for (int i=0; var_buf[i] != '\0'; i++) local_buffer[buf_i++] = var_buf[i];
                } else if (strcmp(token_buffer, "$PWND") == 0) {
                    u32 pwnd = tcp_sk(sk)->prior_cwnd;
                    char var_buf[16] = "\0";
                    sprintf(var_buf, "%d", pwnd);
                    for (int i=0; var_buf[i] != '\0'; i++) local_buffer[buf_i++] = var_buf[i];
                } else if (strcmp(token_buffer, "$PDLV") == 0) {
                    u32 pdlv = tcp_sk(sk)->prr_delivered;
                    char var_buf[16] = "\0";
                    sprintf(var_buf, "%d", pdlv);
                    for (int i=0; var_buf[i] != '\0'; i++) local_buffer[buf_i++] = var_buf[i];
                } else if (strcmp(token_buffer, "$POUT") == 0) {
                    u32 pdlv = tcp_sk(sk)->prr_out;
                    char var_buf[16] = "\0";
                    sprintf(var_buf, "%d", pdlv);
                    for (int i=0; var_buf[i] != '\0'; i++) local_buffer[buf_i++] = var_buf[i];
                } else if (strcmp(token_buffer, "$TIME") == 0) {
                    u64 etime = ktime_get_real_ns() / 1000000;
                    char var_buf[16] = "\0";
                    sprintf(var_buf, "%lld", etime);
                    for (int i=0; var_buf[i] != '\0'; i++) local_buffer[buf_i++] = var_buf[i];
                } else if (strcmp(token_buffer, "$DATA") == 0) {
                    if (strcmp(event_name, tcplog_event_names[IMPLEMENTATION_SPECIFIC]) == 0 && extra != NULL) {
                        if (extra->ev >= 0 && extra->ev < sizeof log_ca_events) {
                            char ca_event_start[] = "\"ca_event\": \"";
                            for (int i=0; ca_event_start[i] != '\0'; i++) local_buffer[buf_i++] = ca_event_start[i];
                            char *event_name = log_ca_events[extra->ev];
                            for (int i=0; event_name[i] != '\0'; i++) local_buffer[buf_i++] = event_name[i];
                            char ca_event_end[] = "\",";
                            for (int i=0; ca_event_end[i] != '\0'; i++) local_buffer[buf_i++] = ca_event_end[i];
                        }
                    }
                } else if (strcmp(token_buffer, "$STAT") == 0) {
                    bool in_slow_start = tcp_in_slow_start(tcp_sk(sk));
                    char state[] = "CONGESTION_AVOIDANCE???";
                    if (in_slow_start)
                        strcpy(state, "SLOW_START");
                    for (int i=0; state[i] != '\0'; i++) local_buffer[buf_i++] = state[i];
                } else if (strcmp(token_buffer, "$SPRT") == 0) {
                    u16 sport = ntohs(sk->__sk_common.skc_num);
                    char var_buf[16] = "\0";
                    sprintf(var_buf, "%d", sport);
                    for (int i=0; var_buf[i] != '\0'; i++) local_buffer[buf_i++] = var_buf[i];
                } else if (strcmp(token_buffer, "$DPRT") == 0) {
                    u16 dport = ntohs(sk->__sk_common.skc_dport);
                    char var_buf[16] = "\0";
                    sprintf(var_buf, "%d", dport);
                    for (int i=0; var_buf[i] != '\0'; i++) local_buffer[buf_i++] = var_buf[i];
                }
            }
            token_buffer[0] = '\0';
            token_i = 0;
            local_buffer[buf_i++] = template_c;
        }
    } while (template_c != '\0' && buf_i < LOG_BUF_ENTRY_SIZE);
    local_buffer[buf_i] = '\0';

    tcplog_log(local_buffer);

    kfree(local_buffer);
}

static int tcplog_device_open(struct inode *inode, struct file *file)
{
    if (tcplog_dev_semaphore)
        return -EBUSY;
    tcplog_dev_semaphore++;
    return 0;
}

static int tcplog_device_release(struct inode *inode, struct file *file)
{
    tcplog_dev_semaphore--;
    return 0;
}

static ssize_t tcplog_device_read(struct file *file, char __user *user_buffer, size_t requested_bytes, loff_t *file_offset)
{
    spin_lock_bh(&tcplog_lock);

    // Wait until buffer is ready for reading
    if (!tcplog_buf_read_ready) {
        spin_unlock_bh(&tcplog_lock);
        if (DMESG_VERBOSE)
            printk("DEV_TCPLOG: WAITING");
        if (wait_event_interruptible(tcplog_wq, tcplog_buf_read_ready))
            return -ERESTARTSYS;
        spin_lock_bh(&tcplog_lock);
    } else {
        if (DMESG_VERBOSE)
            printk("DEV_TCPLOG: NOT WAITING");
    }

    size_t copied = 0;  
    int entries_consumed = 0;
    int entries_available = tcplog_entry_count;

    int i = tcplog_read_index;
    int to_process = entries_available;
    for (int n = 0; n < to_process && requested_bytes > 0; n++) {
        int this_len = tcplog_entry_len[i];
        size_t will_copy = min_t(size_t, (size_t)this_len, requested_bytes);
        if (will_copy) {
            if (copy_to_user(((char __user *)user_buffer) + copied, tcplog_buffer[i], will_copy)) {
                spin_unlock_bh(&tcplog_lock);
                return -EFAULT;
            }
            copied += will_copy;
            requested_bytes -= will_copy;
        }
        i = (i + 1) % LOG_BUF_ENTRY_COUNT_MAX;
        entries_consumed++;
        entries_available--;
        if (i == tcplog_write_index)
            break;
    }

    if (entries_consumed > 0) {
        tcplog_read_index = (tcplog_read_index + entries_consumed) % LOG_BUF_ENTRY_COUNT_MAX;
        tcplog_entry_count = max(0, tcplog_entry_count - entries_consumed);
        tcplog_last_read_time = ktime_get_ns();
    }
    size_t to_copy = copied;

    if (DMESG_VERBOSE)
        printk("DEV_TCPLOG: WRITTEN");

    tcplog_buf_read_ready = false;

    spin_unlock_bh(&tcplog_lock);
    return (ssize_t)to_copy;
}

static ssize_t tcplog_device_write(struct file *filp,
   const char *buff,
   size_t len,
   loff_t *off)
{
   printk ("<1>Sorry, this operation isn't supported.\n");
   return -EINVAL;
}

int log_register(void)
{
    pr_info("TCPlog register\n");

    spin_lock_init(&tcplog_lock);

    register_chrdev(0, DEVICE_NAME, &tcplog_device_ops);

    return tcp_register_congestion_control(&tcp_log_ops);
}

void log_unregister(void)
{
    pr_info("TCPLog unregister. Goodbye.\n");

    tcp_unregister_congestion_control(&tcp_log_ops);
}

static u32 log_get_cwnd(struct sock *sk) {
    return tcp_snd_cwnd(tcp_sk(sk));
}

static u32 log_get_mss(struct sock *sk) {
    struct tcp_sock *tp = tcp_sk(sk);
    // Get maximum segment size based on cached values
    u32 mss = tp->mss_cache ? tp->mss_cache : tp->advmss ? tp->advmss : 1;
    return mss;
}

static u32 log_get_recv_wnd(struct sock *sk) {
    struct tcp_sock *tp = tcp_sk(sk);
    u32 win_bytes = tcp_receive_window(tp);

    u32 mss = log_get_mss(sk); 

    if (!mss)
        return 0;
    return win_bytes / mss;
}

static u32 log_get_initial_wnd(struct sock *sk) {
    u32 win_bytes = tcp_rwnd_init_bpf(sk);

    u32 mss = log_get_mss(sk); 

    if (!mss)
        return 0;
    return win_bytes / mss;
}

static u32 log_get_ssthresh(struct sock *sk) {
    u32 ssthresh = tcp_current_ssthresh(sk);

    u32 mss = log_get_mss(sk); 

    if (!mss)
        return 0;
    return ssthresh / mss;
}

u32 log_ssthresh(struct sock *sk) {
    return tcp_reno_ssthresh(sk);
}

void log_cong_avoid(struct sock *sk, u32 ack, u32 acked) {
    return tcp_reno_cong_avoid(sk, ack, acked);
}

u32 log_undo_cwnd(struct sock *sk) {
    return tcp_reno_undo_cwnd(sk);
}

void log_set_state(struct sock *sk, u8 new_state) {
    char buffer[512];
    sprintf(buffer, "TCPLog: set_state - state=%s - cwnd=%d\n", log_ca_states[new_state], log_get_cwnd(sk));
    tcplog_log(buffer);
    return;
}

void log_cwnd_event(struct sock *sk, enum tcp_ca_event ev) {
    char *event_name = tcplog_event_names[IMPLEMENTATION_SPECIFIC];
    struct tcplog_extra_data data;
    data.ev = ev;
    if (ev == CA_EVENT_TX_START) {
        event_name = tcplog_event_names[CONNECTION_STARTED];
    } else if (ev == CA_EVENT_LOSS) {
        event_name = tcplog_event_names[PACKET_DROPPED];
    }
    tcplog_log_event(event_name, sk, &data);
    return;
}

void log_in_ack_event(struct sock *sk, u32 flags) {
    tcplog_log_event(tcplog_event_names[PACKETS_ACKED], sk, NULL);
    return;
}

static struct tcp_congestion_ops tcp_log_ops = {
    .flags        = TCP_CONG_NON_RESTRICTED,
    .name        = "tcplog",
    .owner        = THIS_MODULE,
    .ssthresh    = log_ssthresh,
    .cong_avoid    = log_cong_avoid,
    .set_state  = log_set_state,
    .cwnd_event = log_cwnd_event,
    .in_ack_event = log_in_ack_event,
    .undo_cwnd    = log_undo_cwnd,
};

module_init(log_register);
module_exit(log_unregister);

MODULE_LICENSE("GPL");