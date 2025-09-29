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
    pr_info("TCPlog unregister. Goodbye.\n");
}

void log_cong_control(struct sock *sk, const struct rate_sample *rs) {
    pr_info("TCPLog: cong_control\n");
    return;
}

u32 log_ssthresh(struct sock *sk) {
    pr_info("TCPLog: ssthresh\n");
    return tcp_reno_ssthresh(sk);
}

void log_cong_avoid(struct sock *sk, u32 ack, u32 acked) {
    pr_info("TCPLog: cong_avoid");
    return tcp_reno_cong_avoid(sk, ack, acked);
}

u32 log_undo_cwnd(struct sock *sk) {
    pr_info("TCPLog: undo_cwnd");
    return tcp_reno_undo_cwnd(sk);
}

static struct tcp_congestion_ops tcp_log_ops = {
	.flags		= TCP_CONG_NON_RESTRICTED,
	.name		= "tcplog",
	.owner		= THIS_MODULE,
	.cong_control	= log_cong_control,
	.ssthresh	= log_ssthresh,
    .cong_avoid	= log_cong_avoid,
	.undo_cwnd	= log_undo_cwnd,
};

module_init(log_register);
module_exit(log_unregister);

MODULE_LICENSE("GPL");