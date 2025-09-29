# Command reference

Some useful commands:

```sh
lsmod
rmmod
insmod
sudo dmesg | tail
sudo dmesg | grep TCPLog
sudo /sbin/sysctl -w net.ipv4.tcp_congestion_control=cubic
sudo /sbin/sysctl -w net.ipv4.tcp_congestion_control=tcplog
sysctl net.ipv4.tcp_available_congestion_control
sysctl net.ipv4.tcp_congestion_control
curl http://ipv4.download.thinkbroadband.com/512MB.zip --output /dev/null # test traffic
```