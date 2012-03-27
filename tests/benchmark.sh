#!/bin/sh

# This script spawns multiple instances of the server and continuously stores
# a single image (gif, composite, 100x100)

SOURCEDIR="`cd \`dirname $0\`/..; pwd`"  # Directory containing the twistd plugin
TMPDIR="/tmp/imagepipe"  # Temporary directory; removed at the end of script!
INSTANCES=1  # How many instances of the server should be spawned
IO_THREADS=1  # How many io threads per instance
TIME=60  # Test duration, see `ab -t`
CONCURRENCY=100  # Number of simulated clients, see `ab -c`
IMAGE="$1"  # Test image
XMLRPC_PRE_PAYLOAD="<?xml version='1.0'?>\r\n<methodCall>\r\n<methodName>store_image</methodName>\r\n<params>\r\n<param>\r\n<value><string>"
XMLRPC_POST_PAYLOAD="</string></value>\r\n</param>\r\n<param>\r\n<value><string>1921.gif</string></value>\r\n</param>\r\n<param>\r\n<value><nil/></value></param>\r\n<param>\r\n<value><struct>\r\n<member>\r\n<name>_small</name>\r\n<value><array><data>\r\n<value><string>100</string></value>\r\n<value><string>100</string></value>\r\n</data></array></value>\r\n</member>\r\n</struct></value>\r\n</param>\r\n<param>\r\n<value><int>1</int></value>\r\n</param>\r\n<param>\r\n<value><int>0</int></value>\r\n</param>\r\n</params>\r\n</methodCall>"

# Here be dragons

if [ $# -lt 1 ]; then
    echo "Usage: $0 path|url"
    exit 1
fi

. `cd \`dirname $0\`; pwd`/functions.sh

pwd=`pwd`
cd $SOURCEDIR || fail "unable to access $SOURCEDIR"

for i in `seq $INSTANCES`; do
    rundir=${TMPDIR}/${i}
    pidfile=${rundir}/twistd.pid
    logfile=${rundir}/twistd.log
    config=${rundir}/imagepipe.ini

    status "Creating environment in $rundir"

    stop_twistd $pidfile
    test -d $rundir && rm -rf $rundir

    mkdir -p $rundir || fail "unable to create $rundir"

    port=`expr 2000 + $i`
    publish_port=`expr 3000 + $i`
    if [ $INSTANCES -eq 1 ]; then
        subscribe_port=3000
    else
        if [ $i -eq 1 ]; then
            subscribe_port=`expr 3000 + $INSTANCES`
        else
            subscribe_port=`expr 3000 + $i - 1`
        fi
    fi

    write_config $config $port $publish_port $subscribe_port $rundir $IO_THREADS || \
        fail "unable to write ${config}"

    status "Starting twistd instance $i (127.0.0.1:${port})"

    start_twistd $rundir $pidfile $logfile $config || \
         fail "unable to start instance; see $logfile for details"
done

cd $pwd

status "Preparing image"

echo $IMAGE | egrep "^https?://" >/dev/null 2>&1
if [ $? -eq 0 ]; then
    wget -NP $TMPDIR $IMAGE || fail "unable to download $IMAGE"
else
    cp $IMAGE $TMPDIR || fail "unable to access $IMAGE"
fi

status "Generating POST data"

payload="${TMPDIR}/payload.xml"
image_name=`basename $IMAGE`
image_path=${TMPDIR}/${image_name}

printf "%b" "$XMLRPC_PRE_PAYLOAD" > $payload
base64 $image_path | sed "s/$/\r/" >> $payload
printf "%b" "$XMLRPC_POST_PAYLOAD" >> $payload

status "Benchmarking (${TIME} second(s))"

# `siege` was the first choice but it refused to handle large POST data
ab -c $CONCURRENCY -t $TIME -T "text/xml" -p $payload -T "text/xml" \
    http://127.0.0.1:2001/

status "Waiting for convert to finish"

while true; do
    pgrep -u `id -u` -l convert | grep " convert$" >/dev/null 2>&1
    if [ $? -ne 0 ]; then
        break
    fi
    sleep 1
done

for i in `seq $INSTANCES`; do
    rundir=${TMPDIR}/${i}
    pidfile=${rundir}/twistd.pid

    status "Shutting down instance $i"
    stop_twistd $pidfile
done

status "Removing ${TMPDIR}"
rm -rf $TMPDIR
