#include <linux/module.h>
#include <linux/printk.h>
#include <net/tcp.h>
#include <linux/inet_diag.h>
#include <linux/inet.h>
#include <linux/string.h>
#include <linux/ktime.h>
#include <linux/spinlock.h>

#include <linux/kprobes.h>

#include "tcplog.h"

#ifdef CA_CUBIC
    #define BASE_CA "cubictcp"
    #pragma message "Using CUBIC CA..."
#elifdef CA_RENO
    #define BASE_CA "tcp_reno"
    #pragma message "Using RENO CA..."
#else
    #define BASE_CA "tcp_reno"
    #pragma message "Using RENO CA (fallback)..."
#endif


static struct tcp_congestion_ops *base_ca_ops = NULL;

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
    "None",
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
    "\t\t\"source_ip\": $SADR,\n"
    "\t\t\"destination_ip\": $DADR,\n"
    "\t\t\"source_port\": $SPRT,\n"
    "\t\t\"destination_port\": $DPRT,\n"
    "\t\t\"in_slow_start\": $STAT,\n"
    "\t\t\"is_cwnd_limited\": $CLIM,\n"
    "\t\t\"state_variables\": {\n"
    "\t\t\t\"cwnd\": $CWND,\n"
    "\t\t\t\"iw\": $IWND,\n"
    "\t\t\t\"rwnd\": $RWND,\n"
    "\t\t\t\"ssthresh\": $STHR,\n"
    "\t\t\t\"delivered\": $DELV,\n"
    "\t\t\t\"in_flight\": $IFLT,\n"
    "\t\t\t\"prior_cwnd\": $PWND,\n"
    "\t\t\t\"prr_delivered\": $PDLV,\n"
    "\t\t\t\"prr_out\": $POUT,\n"
    "\t\t\t\"rtt\": $SRTT\n"
    "\t\t}\n"
    "\t$DATA\n"
    "\t}\n"
    "}\n\x04"; // End-Of-Transmission character for splitting JSON records

#define DMESG_VERBOSE 0
#define DMESG_LOG 0

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

// To lookup tcp_congestion_ops not exported by kernel 
static struct kprobe kp = {
    .symbol_name = "kallsyms_lookup_name",
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

    if (tcplog_entry_count < LOG_BUF_ENTRY_COUNT_MAX)
        tcplog_entry_count = tcplog_entry_count + 1;

    u64 current_time = ktime_get_ns();

    tcplog_last_read_index = tcplog_read_index;

    if (DMESG_VERBOSE)
        printk("DEV_TCPLOG: READY");
    tcplog_buf_read_ready = true;
    tcplog_last_read_time = current_time;
    spin_unlock_bh(&tcplog_lock);
    // wake any readers waiting for new data 
    wake_up_interruptible(&tcplog_wq);
}

void tcplog_log_event(char* event_name, struct sock *sk, struct tcplog_extra_data *extra) {
    char *local_buffer = kmalloc(LOG_BUF_ENTRY_SIZE, GFP_ATOMIC);
    int buf_i = 0;

    char token_buffer[TEMPLATE_TOKEN_SIZE+1] = "\0";
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
                } else if (strcmp(token_buffer, "$DELV") == 0) {
                    u32 delivered = tcp_sk(sk)->delivered;
                    char var_buf[16] = "\0";
                    sprintf(var_buf, "%d", delivered);
                    for (int i=0; var_buf[i] != '\0'; i++) local_buffer[buf_i++] = var_buf[i];
                } else if (strcmp(token_buffer, "$IFLT") == 0) {
                    u32 inflight = tcp_packets_in_flight(tcp_sk(sk));
                    char var_buf[16] = "\0";
                    sprintf(var_buf, "%d", inflight);
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
                            local_buffer[buf_i++] = ',';
                            char ca_event_start[] = "\"ca_event\": \"";
                            for (int i=0; ca_event_start[i] != '\0'; i++) local_buffer[buf_i++] = ca_event_start[i];
                            char *event_name = log_ca_events[extra->ev];
                            for (int i=0; event_name[i] != '\0'; i++) local_buffer[buf_i++] = event_name[i];
                            char ca_event_end[] = "\"";
                            for (int i=0; ca_event_end[i] != '\0'; i++) local_buffer[buf_i++] = ca_event_end[i];
                        }
                    } else if (strcmp(event_name, tcplog_event_names[STATE_UPDATED]) == 0 && extra != NULL) {
                        if (extra->new_state != 0) {
                            char to_start[] = ",\"new\": \"";
                            for (int i=0; to_start[i] != '\0'; i++) local_buffer[buf_i++] = to_start[i];
                            char *to_state_name = log_ca_states[extra->new_state];
                            for (int i=0; to_state_name[i] != '\0'; i++) local_buffer[buf_i++] = to_state_name[i];
                            char to_end[] = "\"";
                            for (int i=0; to_end[i] != '\0'; i++) local_buffer[buf_i++] = to_end[i];
                        }
                    } else if (strcmp(event_name, tcplog_event_names[PACKET_DROPPED]) == 0 && extra != NULL) {
                        if (extra->drop_cause != 0) {
                            local_buffer[buf_i++] = ',';
                            char cause_start[] = "\"cause\": \"";
                            for (int i=0; cause_start[i] != '\0'; i++) local_buffer[buf_i++] = cause_start[i];
                            char *cause_name = tcplog_drop_cause_names[extra->drop_cause];
                            for (int i=0; cause_name[i] != '\0'; i++) local_buffer[buf_i++] = cause_name[i];
                            char cause_end[] = "\"";
                            for (int i=0; cause_end[i] != '\0'; i++) local_buffer[buf_i++] = cause_end[i];
                        }
                    } else if (strcmp(event_name, tcplog_event_names[PACKETS_ACKED]) == 0 && extra && extra->acked) {
                        local_buffer[buf_i++] = ',';
                        char acked_start[] = "\"acked\": ";
                        for (int i=0; acked_start[i] != '\0'; i++) local_buffer[buf_i++] = acked_start[i];
                        char var_buf[16] = "\0";
                        sprintf(var_buf, "%d", extra->acked);
                        for (int i=0; var_buf[i] != '\0'; i++) local_buffer[buf_i++] = var_buf[i];
                    } 
                } else if (strcmp(token_buffer, "$STAT") == 0) {
                    bool in_slow_start = tcp_in_slow_start(tcp_sk(sk));
                    char state[] = "false";
                    if (in_slow_start)
                        strcpy(state, "true");
                    for (int i=0; state[i] != '\0'; i++) local_buffer[buf_i++] = state[i];
                } else if (strcmp(token_buffer, "$CLIM") == 0) {
                    bool is_cwnd_limited = tcp_is_cwnd_limited(sk);
                    char state[] = "false";
                    if (is_cwnd_limited)
                        strcpy(state, "true");
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
                } else if (strcmp(token_buffer, "$SADR") == 0) {
                    char *s_addr = log_ip_to_str(sk->__sk_common.skc_rcv_saddr);
                    for (int i=0; s_addr[i] != '\0'; i++) local_buffer[buf_i++] = s_addr[i];
                    kfree(s_addr);
                } else if (strcmp(token_buffer, "$DADR") == 0) {
                    char *d_addr = log_ip_to_str(sk->__sk_common.skc_daddr);
                    for (int i=0; d_addr[i] != '\0'; i++) local_buffer[buf_i++] = d_addr[i];
                    kfree(d_addr);
                } else if (strcmp(token_buffer, "$SRTT") == 0) { 
                    u32 rtt = log_get_rtt(sk);
                    char var_buf[16] = "\0";
                    sprintf(var_buf, "%d", rtt);
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

    int indices[LOG_BUF_ENTRY_COUNT_MAX];
    size_t lengths[LOG_BUF_ENTRY_COUNT_MAX];
    int entries_consumed = 0;
    size_t total_bytes = 0;

    int entries_available = tcplog_entry_count;
    int i = tcplog_read_index;
    int to_process = entries_available;
    for (int n = 0; n < to_process && total_bytes < requested_bytes; n++) {
        int this_len = tcplog_entry_len[i];

        size_t space_left = (requested_bytes > total_bytes) ? (requested_bytes - total_bytes) : 0;
        if ((size_t)this_len > space_left) {
            break;
        }

        if (entries_consumed < LOG_BUF_ENTRY_COUNT_MAX) {
            indices[entries_consumed] = i;
            lengths[entries_consumed] = this_len;
            total_bytes += this_len;
            entries_consumed++;
        } else {
            break;
        }

        i = (i + 1) % LOG_BUF_ENTRY_COUNT_MAX;
        if (i == tcplog_write_index)
            break;
    }

    if (entries_consumed == 0) {
        spin_unlock_bh(&tcplog_lock);
        return 0;
    }

    // Put buffer into kernel buffer while in lock, write to user outside of lock
    char *kbuf = kmalloc(total_bytes, GFP_ATOMIC);
    if (!kbuf) {
        if (DMESG_VERBOSE)
            printk("DEV_TCPLOG: KMALLOC FAILED");
        spin_unlock_bh(&tcplog_lock);
        return -ENOMEM;
    }

    size_t copied = 0;
    for (int j = 0; j < entries_consumed; j++) {
        int idx = indices[j];
        size_t len = lengths[j];
        memcpy(kbuf + copied, tcplog_buffer[idx], len);
        copied += len;
    }

    int old_read_index = tcplog_read_index;
    int old_entry_count = tcplog_entry_count;

    tcplog_read_index = (tcplog_read_index + entries_consumed) % LOG_BUF_ENTRY_COUNT_MAX;
    tcplog_entry_count = max(0, tcplog_entry_count - entries_consumed);
    tcplog_last_read_time = ktime_get_ns();

    if (DMESG_VERBOSE)
        printk("DEV_TCPLOG: WRITTEN");

    tcplog_buf_read_ready = (tcplog_entry_count > 0);
    spin_unlock_bh(&tcplog_lock);

    if (copy_to_user(user_buffer, kbuf, copied)) {
        spin_lock_bh(&tcplog_lock);
        tcplog_read_index = old_read_index;
        tcplog_entry_count = old_entry_count;
        tcplog_buf_read_ready = true;
        spin_unlock_bh(&tcplog_lock);
        kfree(kbuf);
        return -EFAULT;
    }
    kfree(kbuf);
    return (ssize_t)copied;
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

    int ret = register_kprobe(&kp);
    if (ret < 0) {
        pr_warn("tcplog: register_kprobe failed: %d\n", ret);
    } else if (!kp.addr) {
        pr_warn("tcplog: kprobe registered but kp.addr is NULL\n");
        unregister_kprobe(&kp);
    } else {
        typedef unsigned long (*kallsyms_lookup_name_t)(const char *name);
        kallsyms_lookup_name_t kln = (kallsyms_lookup_name_t)kp.addr;
        unsigned long addr = 0;
        const char *found_name = NULL;

        addr = kln(BASE_CA);
        if (addr)
            found_name = BASE_CA;
        else {
            addr = kln("tcp_reno");
            if (addr)
                found_name = "tcp_reno";
        }

        if (addr) {
            base_ca_ops = (struct tcp_congestion_ops *)addr;
            if (found_name)
                pr_info("tcplog: using %s congestion ops at %px\n", found_name, (void *)addr);
            else
                pr_info("tcplog: found congestion ops at %px, using it\n", (void *)addr);
        } else {
            pr_warn("tcplog: kallsyms_lookup_name failed for preferred CAs, keeping fallback\n");
        }
        unregister_kprobe(&kp);
    }

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
    return tcp_sk(sk)->snd_ssthresh;
}

static u32 log_get_rtt(struct sock *sk) {
    return tcp_sk(sk)->rack.rtt_us;
}

static char* log_ip_to_str(__be32 skc_addr) {
    char *addr_str = kmalloc(23, GFP_ATOMIC);
    u32 u32_addr = ntohl(skc_addr);
    sprintf(addr_str, "\"%d.%d.%d.%d\"", (u32_addr >> 24) & 0xFF,
                                     (u32_addr >> 16) & 0xFF,
                                     (u32_addr >> 8) & 0xFF,
                                     u32_addr & 0xFF);
    return addr_str;
}

u32 log_ssthresh(struct sock *sk) {
    if (base_ca_ops && base_ca_ops->ssthresh)
        return base_ca_ops->ssthresh(sk);
    return tcp_sk(sk)->snd_ssthresh;
}

void log_cong_avoid(struct sock *sk, u32 ack, u32 acked) {
    struct tcplog_extra_data data;
    data.acked = acked;
    tcplog_log_event(tcplog_event_names[PACKETS_ACKED], sk, &data); // cong_avoid called when packets acked (https://github.com/torvalds/linux/blob/944aacb68baf7624ab8d277d0ebf07f025ca137c/net/ipv4/tcp_input.c#L3669)
    if (base_ca_ops && base_ca_ops->cong_avoid)
        base_ca_ops->cong_avoid(sk, ack, acked);
    return;
}

u32 log_undo_cwnd(struct sock *sk) {
    if (base_ca_ops && base_ca_ops->undo_cwnd)
        return base_ca_ops->undo_cwnd(sk);
    return 0;
}

void log_set_state(struct sock *sk, u8 new_state) {
    struct tcplog_extra_data data;
    data.new_state = new_state + 1;
    tcplog_log_event(tcplog_event_names[STATE_UPDATED], sk, &data);

    if (data.new_state == TCP_CA_Recovery + 1) { // Triple duplicate ack occurred https://github.com/torvalds/linux/blob/24d479d26b25bce5faea3ddd9fa8f3a6c3129ea7/net/ipv4/tcp_input.c#L2973
        data.drop_cause = TRIPLE_DUPLICATE_ACKS;
        tcplog_log_event(tcplog_event_names[PACKET_DROPPED], sk, &data);
    } else if (data.new_state == TCP_CA_CWR + 1) {
        data.drop_cause = ECN;
        tcplog_log_event(tcplog_event_names[PACKET_DROPPED], sk, &data);
    } else if (data.new_state == TCP_CA_Loss + 1) {
        data.drop_cause = RETRANSMISSION_TIMEOUT;
        tcplog_log_event(tcplog_event_names[PACKET_DROPPED], sk, &data);
    }

    if (base_ca_ops && base_ca_ops->set_state)
        base_ca_ops->set_state(sk, new_state);
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
        data.drop_cause = RETRANSMISSION_TIMEOUT;
    }
    tcplog_log_event(event_name, sk, &data);
    if (base_ca_ops && base_ca_ops->cwnd_event)
        base_ca_ops->cwnd_event(sk, ev);
    return;
}

void log_in_ack_event(struct sock *sk, u32 flags) {
    // Trigger packet ack log event if not handled by cong_avoid
    // https://github.com/torvalds/linux/blob/944aacb68baf7624ab8d277d0ebf07f025ca137c/net/ipv4/tcp_input.c#L3654
    if (tcp_in_cwnd_reduction(sk))
        tcplog_log_event(tcplog_event_names[PACKETS_ACKED], sk, NULL);
    if (base_ca_ops && base_ca_ops->in_ack_event)
        base_ca_ops->in_ack_event(sk, flags);
    return;
}

void log_init(struct sock *sk) {
    if (base_ca_ops && base_ca_ops->init)
        base_ca_ops->init(sk);
    return;
}

void log_pkts_acked(struct sock *sk, const struct ack_sample *sample) {
    if (base_ca_ops && base_ca_ops->pkts_acked)
        base_ca_ops->pkts_acked(sk, sample);
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

    .init = log_init,
    .pkts_acked = log_pkts_acked,
};

module_init(log_register);
module_exit(log_unregister);

MODULE_LICENSE("GPL");