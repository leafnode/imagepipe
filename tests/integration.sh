#!/bin/sh

# This script spawns multiple instances of the server and stores images using
# the avilable transformations

SOURCEDIR="`cd \`dirname $0\`/..; pwd`"  # Directory containing the twistd plugin
TMPDIR="/tmp/imagepipe"  # Temporary directory; removed at the end of script!
CLIENT="${SOURCEDIR}/examples/client.py"  # Location of the client script
INSTANCES=3  # How many instances of the server should be spawned
IMAGES="$@"  # Test images

# Here be dragons

if [ $# -lt 1 ]; then
    echo "Usage: $0 path|url [path|url...]"
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

    write_config $config $port $publish_port $subscribe_port $rundir 1 || \
        fail "unable to write ${config}"

    status "Starting twistd instance $i (127.0.0.1:${port})"

    start_twistd $rundir $pidfile $logfile $config || \
         fail "unable to start instance; see $logfile for details"
done

cd $pwd

status "Preparing images"

for image in $IMAGES; do
    echo $image | egrep "^https?://" >/dev/null 2>&1
    if [ $? -eq 0 ]; then
        wget -NP $TMPDIR $image || fail "unable to download $image"
    else
        cp $image $TMPDIR || fail "unable to access $image"
    fi
done

status "Storing images"

for image in $IMAGES; do
    image_name=`basename $image`
    image_path=${TMPDIR}/${image_name}

    for i in `seq $INSTANCES`; do
        rundir=${TMPDIR}/${i}
        logfile=${rundir}/twistd.log

        port=`expr 2000 + $i`
        image_name_remote="${i}_${image_name}"

        status "Storing image $image_name_remote to instance ${i}"

        $CLIENT --host=127.0.0.1 --port=$port \
            -i $image_path --remote-path=$image_name_remote || \
                fail "unable to store image; see $logfile for details"

        $CLIENT --host=127.0.0.1 --port=$port \
            -i $image_path --remote-path=$image_name_remote \
            --size="_small 100 100" || \
                fail "unable to store image; see $logfile for details"

        $CLIENT --host=127.0.0.1 --port=$port \
            -i $image_path --remote-path=$image_name_remote \
            --size="_small_composite 100 100" --composite || \
                fail "unable to store image; see $logfile for details"

        $CLIENT --host=127.0.0.1 --port=$port \
            -i $image_path --remote-path=$image_name_remote \
            --size="_small_composite 100 100 png" --composite || \
                fail "unable to store image; see $logfile for details"

        $CLIENT --host=127.0.0.1 --port=$port \
            -i $image_path --remote-path=$image_name_remote \
            --size="_small_crop 100 100" --crop || \
                fail "unable to store image; see $logfile for details"

        status "Waiting for convert to finish"

        while true; do
            pgrep -u `id -u` -l convert | grep " convert$" >/dev/null 2>&1
            if [ $? -ne 0 ]; then
               break
            fi
            sleep 1
        done
    done
done

status "Verifying images"

for image in $IMAGES; do
    image_name=`basename $image`

    for i in `seq $INSTANCES`; do
        rundir=${TMPDIR}/${i}
        logfile=${rundir}/twistd.log
        image_paths="
            ${i}_${image_name}
            ${i}_`echo ${image_name} | sed -r "s/\.(.+)?$/_small.\1/g"`
            ${i}_`echo ${image_name} | sed -r "s/\.(.+)?$/_small_composite.\1/g"`
            ${i}_`echo ${image_name} | sed -r "s/\.(.+)?$/_small_composite.png/g"`
            ${i}_`echo ${image_name} | sed -r "s/\.(.+)?$/_small_crop.\1/g"`
        "

        for image_path in $image_paths; do
            status "${rundir}/$image_path"
            test -f ${rundir}/$image_path || \
                fail "image does not exist; see $logfile for details"
        done

        port=`expr 2000 + $i`

        for image_path in $image_paths; do
            $CLIENT --host=127.0.0.1 --port=$port -d $image_path || \
                fail "unable to remove image; see $logfile for details"
        done
    done
done

for i in `seq $INSTANCES`; do
    rundir=${TMPDIR}/${i}
    pidfile=${rundir}/twistd.pid

    image_paths=`find $rundir -name "*.gif" -or -name "*.jpg" -or -name "*.png" 2>/dev/null`
    if [ ! -z "$image_paths" ]; then
        fail "some image files are still present in ${rundir}"
    fi

    status "Shutting down instance $i"
    stop_twistd $pidfile
done

status "Removing ${TMPDIR}"
rm -rf $TMPDIR
