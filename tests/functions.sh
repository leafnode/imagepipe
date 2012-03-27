# Common functions for test scripts

fail() {
    # $1 = message
    echo "#### Test failed: $1"
    stop_all
    cd $pwd
    exit 1
}

status() {
    # $1 = message
    echo "#### $1"
}

write_config() {
    # $1 = config path
    # $2 = network port
    # $3 = publish port
    # $4 = subscribe port
    # $5 = images path
    # $6 = io threads
    cat << EOF >$1
[network]
interface = 127.0.0.1
port = $2
[replication]
publish = tcp://127.0.0.1:$3
subscribe = tcp://127.0.0.1:$4
[images]
path = $5
io_threads = $6
[imagemagick]
[[env]]
MAGICK_THREAD_LIMIT = 1
EOF
    return $?
}

start_twistd() {
    # $1 = rundir
    # $2 = pidfile
    # $3 = logfile
    # $4 = config
    twistd -d $1 --pidfile $2 --logfile $3 imagepipe -c $4
    sleep 1
    test -f $2 && kill -0 `cat $2` >/dev/null 2>&1
    return $?
}

stop_twistd() {
    # $1 = pidfile
    test -f $1 && kill `cat $1` >/dev/null 2>&1
    sleep 1
    test -f $1 && kill -9 `cat $1` >/dev/null 2>&1
}

stop_all() {
    pidfiles=`find $TMPDIR -name "twistd.pid" 2>/dev/null`
    if [ -z "$pidfiles" ]; then
        return
    fi
    for pidfile in $pidfiles; do
        stop_twistd $pidfile
    done
}
