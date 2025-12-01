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
curl http://ipv4.download.thinkbroadband.com/512MB.zip --output /dev/null # test download
curl -s https://raw.githubusercontent.com/sivel/speedtest-cli/master/speedtest.py | python3 - --no-download --single --secure # test upload
```

## Qlog testing

```sh
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --user-data-dir=/tmp/chrome-profile \
  --no-proxy-server \
  --enable-quic \
  --origin-to-force-quic-on=localhost:443 \
  --host-resolver-rules='MAP localhost:443 127.0.0.1:6121' \
  https://localhost
```