#include <linux/types.h>

#define EVENT_NAMESPACE "tcplog:"

struct tcplog_extra_data {
   u32 ack;
   u32 acked;
   u8 new_state;
   enum tcp_ca_event ev;
   u32 flags;
};

enum TcplogEvents {
   CONNECTION_STARTED,
   PACKET_SENT,
   PACKET_RECEIVED,
   PACKET_DROPPED,
   PACKETS_ACKED,
   STATE_UPDATED,
   IMPLEMENTATION_SPECIFIC
};

static char* tcplog_event_names[] = {
   EVENT_NAMESPACE "connection_started",
   EVENT_NAMESPACE "packet_sent",
   EVENT_NAMESPACE "packet_received",
   EVENT_NAMESPACE "packet_dropped",
   EVENT_NAMESPACE "packets_acked",
   EVENT_NAMESPACE "state_updated",
   EVENT_NAMESPACE "implementation_specific",
};

void tcplog_log(const char *msg);

void tcplog_log_event(char* event_name, struct sock *sk, struct tcplog_extra_data *extra);

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

static u32 log_get_initial_wnd(struct sock *sk);

static u32 log_get_ssthresh(struct sock *sk);

u32 log_ssthresh(struct sock *sk);

void log_cong_avoid(struct sock *sk, u32 ack, u32 acked);

void log_set_state(struct sock *sk, u8 new_state);

void log_cwnd_event(struct sock *sk, enum tcp_ca_event ev);

void log_in_ack_event(struct sock *sk, u32 flags);

u32 log_undo_cwnd(struct sock *sk);

static struct tcp_congestion_ops tcp_log_ops;