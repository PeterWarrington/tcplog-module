#include <linux/types.h>

void tcplog_log(const char *msg);

static int tcplog_device_open(struct inode *inode, struct file *file);

static int tcplog_device_release(struct inode *inode, struct file *file);

static ssize_t tcplog_device_read(struct file *file, char __user *user_buffer, size_t requested_bytes, loff_t *file_offset);

static ssize_t tcplog_device_write(struct file *filp,
   const char *buff,
   size_t len,
   loff_t *off);

int log_register(void);

void log_unregister(void);

static u32 log_get_cwnd(struct sock *sk);

static u32 log_get_mss(struct sock *sk);

static u32 log_get_recv_wnd(struct sock *sk);

static u32 log_get_snd_wnd(struct sock *sk);

u32 log_ssthresh(struct sock *sk);

void log_cong_avoid(struct sock *sk, u32 ack, u32 acked);

void log_set_state(struct sock *sk, u8 new_state);

void log_cwnd_event(struct sock *sk, enum tcp_ca_event ev);

void log_in_ack_event(struct sock *sk, u32 flags);

u32 log_undo_cwnd(struct sock *sk);

static struct tcp_congestion_ops tcp_log_ops;