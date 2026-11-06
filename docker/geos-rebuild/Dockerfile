# E5: the study's pinned development image with only GEOS rebuilt at one commit.
#
#   docker build -t tavs-geos:before-fc3eca90 --build-arg GEOS_COMMIT=fc3eca9063096a665700651d6523f56de4dae415 docker/geos-rebuild
#   docker build -t tavs-geos:fix-2c8e04fa    --build-arg GEOS_COMMIT=2c8e04faf8235456b417979bcf23271ef34148a7 docker/geos-rebuild
#
# The base image (PostgreSQL 18, PostGIS 3.7.0dev, GEOS 3.16.0dev at 283e8272) keeps GEOS in
# /usr/local: libgeos_c.so.1 -> libgeos_c.so.1.23.0 and libgeos.so.3.16.0, built by
# docker-postgis with `cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF` (IPO off).
# PostGIS (/usr/lib/postgresql/18/lib/postgis-3.so) links libgeos_c.so.1 and is not rebuilt.
# The builder stage compiles GEOS the same way; the final stage removes the base image's GEOS
# libraries, copies the new install tree over /usr/local, and fails if PostGIS does not resolve
# to the new files. The toolchain stays in the builder stage, so the final image differs from
# the base only in GEOS files and the marker files /_tavs_geos_commit.txt (the 40-character
# commit) and /_tavs_geos_build.txt (git log, cmake flags, SHA-256 of the built libraries).

ARG BASE_IMAGE=postgis/postgis@sha256:620f1f1ffb479ffbda686dbfde113557a9859cdf9de0f86683b0702846915107

FROM ${BASE_IMAGE} AS builder
# Toolchain layer first and independent of GEOS_COMMIT, so both images share the same cached
# compiler packages (a build arg declared earlier would be part of this layer's cache key).
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates git cmake make g++; \
    rm -rf /var/lib/apt/lists/*
ARG GEOS_COMMIT
ARG JOBS=6
RUN set -eux; \
    test -n "${GEOS_COMMIT}"; \
    cd /usr/src; \
    git clone https://github.com/libgeos/geos.git; \
    cd geos; \
    git checkout --detach "${GEOS_COMMIT}"; \
    test "$(git rev-parse HEAD)" = "${GEOS_COMMIT}"; \
    mkdir cmake-build; \
    cd cmake-build; \
    cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DCMAKE_INSTALL_PREFIX=/usr/local \
             -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=OFF; \
    make -j"${JOBS}"; \
    make install DESTDIR=/stage; \
    test -f /stage/usr/local/lib/libgeos_c.so.1.23.0; \
    test -f /stage/usr/local/lib/libgeos.so.3.16.0; \
    { echo "GEOS_COMMIT=${GEOS_COMMIT}"; \
      echo "git describe: $(git -C /usr/src/geos describe --tags --always)"; \
      git -C /usr/src/geos log -1; \
      echo "cmake: -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DCMAKE_INSTALL_PREFIX=/usr/local -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=OFF; make -j${JOBS}"; \
      echo "compiler: $(g++ --version | head -1)"; \
      echo "sha256 of the built libraries:"; \
      cd /stage/usr/local/lib && sha256sum libgeos_c.so.1.23.0 libgeos.so.3.16.0; \
    } > /stage/_tavs_geos_build.txt; \
    echo "${GEOS_COMMIT}" > /stage/_tavs_geos_commit.txt

FROM ${BASE_IMAGE}
ARG GEOS_COMMIT
LABEL tavs.geos.commit="${GEOS_COMMIT}" \
      tavs.geos.base="postgis/postgis@sha256:620f1f1ffb479ffbda686dbfde113557a9859cdf9de0f86683b0702846915107"
RUN set -eux; \
    rm -f /usr/local/lib/libgeos.so /usr/local/lib/libgeos.so.3.16.0 \
          /usr/local/lib/libgeos_c.so /usr/local/lib/libgeos_c.so.1 /usr/local/lib/libgeos_c.so.1.23.0
COPY --from=builder /stage/usr/local/ /usr/local/
COPY --from=builder /stage/_tavs_geos_commit.txt /stage/_tavs_geos_build.txt /
RUN set -eux; \
    ldconfig; \
    test "$(cat /_tavs_geos_commit.txt)" = "${GEOS_COMMIT}"; \
    ldd /usr/lib/postgresql/18/lib/postgis-3.so | grep geos; \
    if ldd /usr/lib/postgresql/18/lib/postgis-3.so | grep -q 'not found'; then exit 1; fi; \
    ldd /usr/lib/postgresql/18/lib/postgis-3.so | grep -q 'libgeos_c.so.1 => /usr/local/lib/libgeos_c.so.1 '; \
    cd /usr/local/lib; \
    sed -n '/^sha256 of the built libraries:/,$p' /_tavs_geos_build.txt | tail -n +2 | sha256sum -c -; \
    test "$(readlink -f /usr/local/lib/libgeos_c.so.1)" = /usr/local/lib/libgeos_c.so.1.23.0; \
    geos-config --version
