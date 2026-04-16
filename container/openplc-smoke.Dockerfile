FROM debian:trixie-20251020

ARG HTTP_PROXY=
ARG HTTPS_PROXY=
ARG ALL_PROXY=
ARG http_proxy=
ARG https_proxy=
ARG all_proxy=

COPY . /workdir

WORKDIR /workdir

RUN mkdir /docker_persistent

VOLUME /docker_persistent

RUN find /workdir -type f \( \
        -name "*.sh" -o \
        -name "*.ac" -o \
        -name "*.am" -o \
        -name "*.m4" -o \
        -name "*.c" -o \
        -name "*.cc" -o \
        -name "*.cpp" -o \
        -name "*.h" -o \
        -name "*.hh" -o \
        -name "*.l" -o \
        -name "*.y" -o \
        -name "configure" -o \
        -name "configure.ac" -o \
        -name "Makefile*" -o \
        -path "*/config/*" \
    \) -exec sed -i 's/\r$//' {} + \
    && ./install.sh docker \
    && test -f /workdir/start_openplc.sh \
    && test -f /workdir/webserver/iec2c \
    && touch /docker_persistent/mbconfig.cfg \
    && touch /docker_persistent/persistent.file \
    && mkdir /docker_persistent/st_files \
    && cp /workdir/webserver/openplc.db /docker_persistent/openplc.db \
    && mv /workdir/webserver/openplc.db /workdir/webserver/openplc_default.db \
    && cp /workdir/webserver/dnp3.cfg /docker_persistent/dnp3.cfg \
    && mv /workdir/webserver/dnp3.cfg /workdir/webserver/dnp3_default.cfg \
    && cp -r /workdir/webserver/st_files/ /docker_persistent/st_files/ \
    && mv /workdir/webserver/st_files /workdir/webserver/st_files_default \
    && cp /workdir/webserver/active_program /docker_persistent/active_program \
    && mv /workdir/webserver/active_program /workdir/webserver/active_program_default \
    && ln -s /docker_persistent/mbconfig.cfg /workdir/webserver/mbconfig.cfg \
    && ln -s /docker_persistent/persistent.file /workdir/webserver/persistent.file \
    && ln -s /docker_persistent/openplc.db /workdir/webserver/openplc.db \
    && ln -s /docker_persistent/dnp3.cfg /workdir/webserver/dnp3.cfg \
    && ln -s /docker_persistent/st_files /workdir/webserver/st_files \
    && ln -s /docker_persistent/active_program /workdir/webserver/active_program

ENTRYPOINT ["./start_openplc.sh"]
