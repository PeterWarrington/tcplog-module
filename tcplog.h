#include <linux/types.h>

int log_register(void);

void log_unregister(void);

void log_cong_control(struct sock *sk, const struct rate_sample *rs);

u32 log_ssthresh(struct sock *sk);

void log_cong_avoid(struct sock *sk, u32 ack, u32 acked);

u32 log_undo_cwnd(struct sock *sk);

static struct tcp_congestion_ops tcp_log_ops;