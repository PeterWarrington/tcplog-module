#include <linux/module.h>
#include <linux/printk.h>
#include <net/tcp.h>
#include <linux/inet_diag.h>
#include <linux/inet.h>

#include "tcplog.h"

int log_register(void)
{
    pr_info("TCPlog register\n");

    return tcp_register_congestion_control(&tcp_log_ops);
}

void log_unregister(void)
{
    pr_info("TCPLog unregister. Goodbye.\n");
}

static u32 log_get_cwnd(struct sock *sk) {
    return tcp_snd_cwnd(tcp_sk(sk));
}

u32 log_ssthresh(struct sock *sk) {
    pr_info("TCPLog: ssthresh\n");
    return tcp_reno_ssthresh(sk);
}

void log_cong_avoid(struct sock *sk, u32 ack, u32 acked) {
    pr_info("TCPLog: cong_avoid - cwnd=%d\n", log_get_cwnd(sk));
    return tcp_reno_cong_avoid(sk, ack, acked);
}

u32 log_undo_cwnd(struct sock *sk) {
    pr_info("TCPLog: undo_cwnd");
    return tcp_reno_undo_cwnd(sk);
}

void log_set_state(struct sock *sk, u8 new_state) {
    pr_info("TCPLog: log_set_state - state=%d - cwnd=%d\n", new_state, log_get_cwnd(sk));
    return;
}

void log_cwnd_event(struct sock *sk, enum tcp_ca_event ev) {
    pr_info("TCPLog: cwnd_event - ev=%d, cwnd=%d\n", ev, log_get_cwnd(sk));
    return;
}

void log_in_ack_event(struct sock *sk, u32 flags) {
    pr_info("TCPLog: in_ack_event - cwnd=%d\n", log_get_cwnd(sk));
    return;
}

static struct tcp_congestion_ops tcp_log_ops = {
	.flags		= TCP_CONG_NON_RESTRICTED,
	.name		= "tcplog",
	.owner		= THIS_MODULE,
	.ssthresh	= log_ssthresh,
    .cong_avoid	= log_cong_avoid,
    .set_state  = log_set_state,
    .cwnd_event = log_cwnd_event,
    .in_ack_event = log_in_ack_event,
	.undo_cwnd	= log_undo_cwnd,
};

module_init(log_register);
module_exit(log_unregister);

MODULE_LICENSE("GPL");