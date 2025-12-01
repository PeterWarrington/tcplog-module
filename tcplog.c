#include <linux/module.h>
#include <linux/printk.h>
#include <net/tcp.h>
#include <linux/inet_diag.h>
#include <linux/inet.h>
#include <linux/string.h>

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

// For Character Device logging
#define DEVICE_NAME "tcplog"
#define LOG_BUF_SIZE 4096
static DEFINE_MUTEX(tcplog_mutex);
static int tcplog_device_semaphore = 0;
static char tcplog_buffer[LOG_BUF_SIZE];
static int tcplog_pos = 0;
static struct file_operations tcplog_device_ops = {
  .read = tcplog_device_read,
  .write = tcplog_device_write,
  .open = tcplog_device_open,
  .release = tcplog_device_release
};

void tcplog_log(const char *msg)
{
    int msg_len = strlen(msg);

    mutex_lock(&tcplog_mutex);
    
    if (tcplog_pos + msg_len >= LOG_BUF_SIZE)
        tcplog_pos = 0; // wrap-around

    memcpy(tcplog_buffer + tcplog_pos, msg, msg_len);
    tcplog_pos += msg_len;

    mutex_unlock(&tcplog_mutex);
}

static int tcplog_device_open(struct inode *inode, struct file *file)
{
    if (tcplog_device_semaphore) return -EBUSY;
    tcplog_device_semaphore++;

    return 0;
}

static int tcplog_device_release(struct inode *inode, struct file *file)
{
    tcplog_device_semaphore--;
    return 0;
}

static ssize_t tcplog_device_read(struct file *file, char __user *user_buffer, size_t requested_bytes, loff_t *file_offset)
{
    size_t available_bytes;
    size_t bytes_to_copy;

    mutex_lock(&tcplog_mutex);

    if (*file_offset >= tcplog_pos) {
        mutex_unlock(&tcplog_mutex);
        return 0; // EOF
    }

    available_bytes = tcplog_pos - *file_offset;

    bytes_to_copy = min(available_bytes, requested_bytes);

    if (copy_to_user(user_buffer, tcplog_buffer + *file_offset, bytes_to_copy)) {
        mutex_unlock(&tcplog_mutex);
        return -EFAULT;
    }

    *file_offset += bytes_to_copy;

    mutex_unlock(&tcplog_mutex);

    return bytes_to_copy;
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

static u32 log_get_snd_wnd(struct sock *sk) {
    struct tcp_sock *tp = tcp_sk(sk);
    u32 win_bytes = tp->snd_wnd;

    u32 mss = log_get_mss(sk); 

    if (!mss)
        return 0;
    return win_bytes / mss;
}

u32 log_ssthresh(struct sock *sk) {
    tcplog_log("TCPLog: ssthresh\n");
    return tcp_reno_ssthresh(sk);
}

void log_cong_avoid(struct sock *sk, u32 ack, u32 acked) {
    char buffer[512];
    sprintf(buffer, "TCPLog: cong_avoid - cwnd=%d\n", log_get_cwnd(sk));
    tcplog_log(buffer);
    return tcp_reno_cong_avoid(sk, ack, acked);
}

u32 log_undo_cwnd(struct sock *sk) {
    tcplog_log("TCPLog: undo_cwnd");
    return tcp_reno_undo_cwnd(sk);
}

void log_set_state(struct sock *sk, u8 new_state) {
    char buffer[512];
    sprintf(buffer, "TCPLog: set_state - state=%s - cwnd=%d\n", log_ca_states[new_state], log_get_cwnd(sk));
    tcplog_log(buffer);
    return;
}

void log_cwnd_event(struct sock *sk, enum tcp_ca_event ev) {
    char buffer[512];
    sprintf(buffer, "TCPLog: cwnd_event - ev=%s, cwnd=%d\n", log_ca_events[ev], log_get_cwnd(sk));
    tcplog_log(buffer);
    return;
}

void log_in_ack_event(struct sock *sk, u32 flags) {
    char buffer[512];
    sprintf(buffer, "TCPLog: in_ack_event - cwnd=%d, recv_wnd=%d, snd_wnd=%d\n",
            log_get_cwnd(sk), log_get_recv_wnd(sk), log_get_snd_wnd(sk));
    tcplog_log(buffer);
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