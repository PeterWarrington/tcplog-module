obj-m += tcplog.o

PWD := $(CURDIR)

all:
	$(MAKE) -C /lib/modules/$(shell uname -r)/build M=$(PWD) modules

clean:
	$(MAKE) -C /lib/modules/$(shell uname -r)/build M=$(PWD) clean

install: uninstall all
	-sudo insmod ./tcplog.ko
	sudo /sbin/sysctl -w net.ipv4.tcp_congestion_control=tcplog
	-sudo rm -f /dev/tcplog
	bash -c 'MAJOR=$$(cat /proc/devices | grep -P "\d* tcplog" | grep -Po "\d*" | tail -1); sudo mknod /dev/tcplog c "$$MAJOR" 0'

all-install: all install

uninstall:
	-sudo rm -f /dev/tcplog
	-sudo ifconfig enp0s3 down
	-sudo /sbin/sysctl -w net.ipv4.tcp_congestion_control=cubic
	-sudo rmmod tcplog -f
	-sudo ifconfig enp0s3 up

test-upload:
	curl -s https://raw.githubusercontent.com/sivel/speedtest-cli/master/speedtest.py | python3 - --no-download --single

test-download:
	curl http://ipv4.download.thinkbroadband.com/512MB.zip --output /dev/null

test-tiny:
	curl http://example.com --output /dev/null

test-lossy:
	nc 192.0.2.1 5555 < /dev/random

view-log:
	tail +1f /dev/tcplog

dmesg:
	sudo dmesg -w

mininet:
	vagrant up
	vagrant ssh -c "cd tcplog-module && sudo python3 scripts/mininet_tester.py -o log/test-mininet.json"

test:
	vagrant up
	vagrant ssh -c "cd tcplog-module && sudo python3 scripts/test_runner.py"