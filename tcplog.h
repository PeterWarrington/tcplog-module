#include <linux/types.h>

int log_register(void);

void log_unregister(void);

static u32 log_get_cwnd(struct sock *sk);

u32 log_ssthresh(struct sock *sk);

void log_cong_avoid(struct sock *sk, u32 ack, u32 acked);

void log_set_state(struct sock *sk, u8 new_state);

void log_cwnd_event(struct sock *sk, enum tcp_ca_event ev);

void log_in_ack_event(struct sock *sk, u32 flags);

u32 log_undo_cwnd(struct sock *sk);

static struct tcp_congestion_ops tcp_log_ops;