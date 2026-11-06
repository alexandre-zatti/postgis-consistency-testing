# E5: family A replay on GEOS before and after the fix (GEOS PR #1590)

- Command: `python.exe -s -m tavs.replay_fix`
- Working directory: `C:\Users\Ale\masters\coursework\MCET063 - Tópicos em Testes Automatizados e Verificação de Software (2026-2)\final-project\experiment`
- Start: 2026-11-06 14:51:42 -0300; end: 2026-11-06 15:52:22 -0300
- Repository HEAD: 03c911c8826c2ce520b650127071fced9143843c; uncommitted changes in tavs/, docker/, scripts/: ?? docker/; ?? scripts/run_e5_geos_fix.ps1; ?? tavs/posthoc_moves.py; ?? tavs/replay_fix.py
- Python 3.14.7, Windows-11-10.0.26300-SP0
- Inputs: ['C:\\Users\\Ale\\masters\\coursework\\MCET063 - Tópicos em Testes Automatizados e Verificação de Software (2026-2)\\final-project\\experiment\\runs\\e3\\triage\\families.csv', 'C:\\Users\\Ale\\masters\\coursework\\MCET063 - Tópicos em Testes Automatizados e Verificação de Software (2026-2)\\final-project\\experiment\\runs\\e3\\triage\\findings.json', 'C:\\Users\\Ale\\masters\\coursework\\MCET063 - Tópicos em Testes Automatizados e Verificação de Software (2026-2)\\final-project\\experiment\\findings\\A-relateng-crash-empty-polygon\\reproduce.sql']
- Findings: 254 of family A (families.csv family == A); selection: {'limit': None, 'keys': None}
- Crash check: `triage.crash_probes(rep_item)` on the shrunk pair through `triage.run_probe`; a finding crashes when any probe's error is `crash`.
- Image builds: `docker build --progress=plain -t <tag> --build-arg GEOS_COMMIT=<commit> --build-arg JOBS=6 --build-arg BASE_IMAGE=<dev digest> docker/geos-rebuild` (scripts/run_e5_geos_fix.ps1; full output in log.txt)

## Counts per target

| target | image | GEOS marker | verified | findings crashed | probes crashed | probes other error | reproducer with_empty |
|---|---|---|---|---|---|---|---|
| before | `tavs-geos:before-fc3eca90` | fc3eca9063096a665700651d6523f56de4dae415 | True / after True | 254 / 254 (of 254) | 748 / 1428 | 0 / 1428 | CRASH |
| fix | `tavs-geos:fix-2c8e04fa` | 2c8e04faf8235456b417979bcf23271ef34148a7 | True / after True | 0 / 254 (of 254) | 0 / 1428 | 0 / 1428 | [["FF20F1FF2"]] |
| dev | `postgis/postgis@sha256:620f1f1ffb479ffbda686dbfde113557a9859cdf9de0f86683b0702846915107` | - | True / after True | 254 / 254 (of 254) | 748 / 1428 | 0 / 1428 | CRASH |

Probe lists identical to the triage's recorded probes: before 254 / 254, fix 254 / 254, dev 254 / 254

Anchor agreement with the triage record (crash yes/no per finding):

- before vs triage `dev`: 254 / 254 agree
- before vs triage `current`: 254 / 254 agree
- fix vs triage `dev`: 0 / 254 agree
- fix vs triage `current`: 0 / 254 agree
- dev vs triage `dev`: 254 / 254 agree
- dev vs triage `current`: 254 / 254 agree

## Targets

### before

- Image: `tavs-geos:before-fc3eca90`; id `sha256:83b7d97ddbb26dd27794584583cb3e41a1ba06253d5282b4af1d6ae94815b2d0`; digests ['tavs-geos@sha256:83b7d97ddbb26dd27794584583cb3e41a1ba06253d5282b4af1d6ae94815b2d0']; created 2026-11-06T17:47:59.735476391Z; label tavs.geos.commit fc3eca9063096a665700651d6523f56de4dae415
- Container image id: `sha256:83b7d97ddbb26dd27794584583cb3e41a1ba06253d5282b4af1d6ae94815b2d0`
- Expected GEOS commit: fc3eca9063096a665700651d6523f56de4dae415
- Start 2026-11-06 14:51:42 -0300, end 2026-11-06 15:21:24 -0300
- docker run: `docker run -d --rm --name tavs-e5-before-13384 --label tavs.e5=1 -e POSTGRES_PASSWORD=postgis --shm-size 256m -p 127.0.0.1:55616:5432 tavs-geos:before-fc3eca90 postgres -c fsync=off -c synchronous_commit=off -c full_page_writes=off`
- verify_before: ok=True problems=[]
  - postgis_geos_version: `3.16.0dev-CAPI-1.23.0 3.15.0rc1-54-gfc3eca906`
  - marker /_tavs_geos_commit.txt: fc3eca9063096a665700651d6523f56de4dae415; base image marker: commit 283e82726fbd5ecc45397f182e12e056a65b2dd7; GEOS version names the commit: True
  - PostGIS library: `/usr/lib/postgresql/18/lib/postgis-3.so`; ldd: `libgeos_c.so.1 => /usr/local/lib/libgeos_c.so.1 (0x0000775371739000) | libgeos.so.3.16.0 => /usr/local/lib/libgeos.so.3.16.0 (0x000077536ff14000)`
  - backend 87 maps: ['/usr/local/lib/libgeos_c.so.1.23.0', '/usr/local/lib/libgeos.so.3.16.0']
  - sha256 (runtime): {'/usr/local/lib/libgeos.so.3.16.0': 'cd44f1f49c3c707ded8b051dc094954cce0ca632d1092dfd6e8222fa71c0b86e', '/usr/local/lib/libgeos_c.so.1.23.0': 'b3264e7779e1f228fa286b5e1e87a2176f5d613a82738ba3134bc757aa5bdc8c'}
  - sha256 (build record): {'libgeos_c.so.1.23.0': 'b3264e7779e1f228fa286b5e1e87a2176f5d613a82738ba3134bc757aa5bdc8c', 'libgeos.so.3.16.0': 'cd44f1f49c3c707ded8b051dc094954cce0ca632d1092dfd6e8222fa71c0b86e'}
  - build record /_tavs_geos_build.txt:

```
GEOS_COMMIT=fc3eca9063096a665700651d6523f56de4dae415
git describe: 3.15.0rc1-54-gfc3eca906
commit fc3eca9063096a665700651d6523f56de4dae415
Author: Daniel Baston <dbaston@gmail.com>
Date:   Thu Nov 5 09:10:08 2026 -0500

    GridIntersection: robustness fixes (#1589)
    
    Co-authored-by: Alejandro Pacheco <ale@alepacheco.dev>
cmake: -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DCMAKE_INSTALL_PREFIX=/usr/local -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=OFF; make -j6
compiler: g++ (Debian 14.2.0-19) 14.2.0
sha256 of the built libraries:
b3264e7779e1f228fa286b5e1e87a2176f5d613a82738ba3134bc757aa5bdc8c  libgeos_c.so.1.23.0
cd44f1f49c3c707ded8b051dc094954cce0ca632d1092dfd6e8222fa71c0b86e  libgeos.so.3.16.0
```

- verify_after: ok=True problems=[]
  - postgis_geos_version: `3.16.0dev-CAPI-1.23.0 3.15.0rc1-54-gfc3eca906`
  - marker /_tavs_geos_commit.txt: fc3eca9063096a665700651d6523f56de4dae415; base image marker: commit 283e82726fbd5ecc45397f182e12e056a65b2dd7; GEOS version names the commit: True
  - PostGIS library: `/usr/lib/postgresql/18/lib/postgis-3.so`; ldd: `libgeos_c.so.1 => /usr/local/lib/libgeos_c.so.1 (0x00007fa1a99a3000) | libgeos.so.3.16.0 => /usr/local/lib/libgeos.so.3.16.0 (0x00007fa1a817e000)`
  - backend 7638 maps: ['/usr/local/lib/libgeos_c.so.1.23.0', '/usr/local/lib/libgeos.so.3.16.0']
  - sha256 (runtime): {'/usr/local/lib/libgeos.so.3.16.0': 'cd44f1f49c3c707ded8b051dc094954cce0ca632d1092dfd6e8222fa71c0b86e', '/usr/local/lib/libgeos_c.so.1.23.0': 'b3264e7779e1f228fa286b5e1e87a2176f5d613a82738ba3134bc757aa5bdc8c'}
  - sha256 (build record): {'libgeos_c.so.1.23.0': 'b3264e7779e1f228fa286b5e1e87a2176f5d613a82738ba3134bc757aa5bdc8c', 'libgeos.so.3.16.0': 'cd44f1f49c3c707ded8b051dc094954cce0ca632d1092dfd6e8222fa71c0b86e'}
- 2026-11-06 14:51:43 -0300 started tavs-e5-before-13384 from tavs-geos:before-fc3eca90 on 127.0.0.1:55616
- 2026-11-06 15:21:24 -0300 removed tavs-e5-before-13384: rc=0

### fix

- Image: `tavs-geos:fix-2c8e04fa`; id `sha256:a9136b58b9bf8ed85d59387a8500c6194242e8933603708e44f604e01d92a4c4`; digests ['tavs-geos@sha256:a9136b58b9bf8ed85d59387a8500c6194242e8933603708e44f604e01d92a4c4']; created 2026-11-06T17:51:35.608543627Z; label tavs.geos.commit 2c8e04faf8235456b417979bcf23271ef34148a7
- Container image id: `sha256:a9136b58b9bf8ed85d59387a8500c6194242e8933603708e44f604e01d92a4c4`
- Expected GEOS commit: 2c8e04faf8235456b417979bcf23271ef34148a7
- Start 2026-11-06 15:21:24 -0300, end 2026-11-06 15:21:38 -0300
- docker run: `docker run -d --rm --name tavs-e5-fix-13384 --label tavs.e5=1 -e POSTGRES_PASSWORD=postgis --shm-size 256m -p 127.0.0.1:55605:5432 tavs-geos:fix-2c8e04fa postgres -c fsync=off -c synchronous_commit=off -c full_page_writes=off`
- verify_before: ok=True problems=[]
  - postgis_geos_version: `3.16.0dev-CAPI-1.23.0 3.15.0rc1-55-g2c8e04faf`
  - marker /_tavs_geos_commit.txt: 2c8e04faf8235456b417979bcf23271ef34148a7; base image marker: commit 283e82726fbd5ecc45397f182e12e056a65b2dd7; GEOS version names the commit: True
  - PostGIS library: `/usr/lib/postgresql/18/lib/postgis-3.so`; ldd: `libgeos_c.so.1 => /usr/local/lib/libgeos_c.so.1 (0x0000792c38791000) | libgeos.so.3.16.0 => /usr/local/lib/libgeos.so.3.16.0 (0x0000792c36f6c000)`
  - backend 87 maps: ['/usr/local/lib/libgeos_c.so.1.23.0', '/usr/local/lib/libgeos.so.3.16.0']
  - sha256 (runtime): {'/usr/local/lib/libgeos.so.3.16.0': 'e2face6bb767b6f9dcb7e3dd6b3311d9d40324ade5c1ea656134c35b08f12b7b', '/usr/local/lib/libgeos_c.so.1.23.0': '4bdad7e25eee2841d4964350f60c57a17ead6d817a36c9d4147eea2455aff7d6'}
  - sha256 (build record): {'libgeos_c.so.1.23.0': '4bdad7e25eee2841d4964350f60c57a17ead6d817a36c9d4147eea2455aff7d6', 'libgeos.so.3.16.0': 'e2face6bb767b6f9dcb7e3dd6b3311d9d40324ade5c1ea656134c35b08f12b7b'}
  - build record /_tavs_geos_build.txt:

```
GEOS_COMMIT=2c8e04faf8235456b417979bcf23271ef34148a7
git describe: 3.15.0rc1-55-g2c8e04faf
commit 2c8e04faf8235456b417979bcf23271ef34148a7
Author: Daniel Baston <dbaston@gmail.com>
Date:   Thu Nov 5 09:10:33 2026 -0500

    AdjacentEdgeLocator: Avoid checking empty rings (#1590)
    
    Resolves https://github.com/libgeos/geos/issues/1585
cmake: -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DCMAKE_INSTALL_PREFIX=/usr/local -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=OFF; make -j6
compiler: g++ (Debian 14.2.0-19) 14.2.0
sha256 of the built libraries:
4bdad7e25eee2841d4964350f60c57a17ead6d817a36c9d4147eea2455aff7d6  libgeos_c.so.1.23.0
e2face6bb767b6f9dcb7e3dd6b3311d9d40324ade5c1ea656134c35b08f12b7b  libgeos.so.3.16.0
```

- verify_after: ok=True problems=[]
  - postgis_geos_version: `3.16.0dev-CAPI-1.23.0 3.15.0rc1-55-g2c8e04faf`
  - marker /_tavs_geos_commit.txt: 2c8e04faf8235456b417979bcf23271ef34148a7; base image marker: commit 283e82726fbd5ecc45397f182e12e056a65b2dd7; GEOS version names the commit: True
  - PostGIS library: `/usr/lib/postgresql/18/lib/postgis-3.so`; ldd: `libgeos_c.so.1 => /usr/local/lib/libgeos_c.so.1 (0x000071aa3d334000) | libgeos.so.3.16.0 => /usr/local/lib/libgeos.so.3.16.0 (0x000071aa3bb0f000)`
  - backend 147 maps: ['/usr/local/lib/libgeos_c.so.1.23.0', '/usr/local/lib/libgeos.so.3.16.0']
  - sha256 (runtime): {'/usr/local/lib/libgeos.so.3.16.0': 'e2face6bb767b6f9dcb7e3dd6b3311d9d40324ade5c1ea656134c35b08f12b7b', '/usr/local/lib/libgeos_c.so.1.23.0': '4bdad7e25eee2841d4964350f60c57a17ead6d817a36c9d4147eea2455aff7d6'}
  - sha256 (build record): {'libgeos_c.so.1.23.0': '4bdad7e25eee2841d4964350f60c57a17ead6d817a36c9d4147eea2455aff7d6', 'libgeos.so.3.16.0': 'e2face6bb767b6f9dcb7e3dd6b3311d9d40324ade5c1ea656134c35b08f12b7b'}
- 2026-11-06 15:21:25 -0300 started tavs-e5-fix-13384 from tavs-geos:fix-2c8e04fa on 127.0.0.1:55605
- 2026-11-06 15:21:38 -0300 removed tavs-e5-fix-13384: rc=0

### dev

- Image: `postgis/postgis@sha256:620f1f1ffb479ffbda686dbfde113557a9859cdf9de0f86683b0702846915107`; id `sha256:620f1f1ffb479ffbda686dbfde113557a9859cdf9de0f86683b0702846915107`; digests ['postgis/postgis@sha256:620f1f1ffb479ffbda686dbfde113557a9859cdf9de0f86683b0702846915107']; created 2026-10-26T16:45:03.933442504Z; label tavs.geos.commit None
- Container image id: `sha256:620f1f1ffb479ffbda686dbfde113557a9859cdf9de0f86683b0702846915107`
- Expected GEOS commit: (none: anchor)
- Start 2026-11-06 15:21:39 -0300, end 2026-11-06 15:52:22 -0300
- docker run: `docker run -d --rm --name tavs-e5-dev-13384 --label tavs.e5=1 -e POSTGRES_PASSWORD=postgis --shm-size 256m -p 127.0.0.1:55621:5432 postgis/postgis@sha256:620f1f1ffb479ffbda686dbfde113557a9859cdf9de0f86683b0702846915107 postgres -c fsync=off -c synchronous_commit=off -c full_page_writes=off`
- verify_before: ok=True problems=[]
  - postgis_geos_version: `3.16.0dev-CAPI-1.23.0 3.15.0rc1-41-g283e82726`
  - marker /_tavs_geos_commit.txt: None; base image marker: commit 283e82726fbd5ecc45397f182e12e056a65b2dd7; GEOS version names the commit: None
  - PostGIS library: `/usr/lib/postgresql/18/lib/postgis-3.so`; ldd: `libgeos_c.so.1 => /usr/local/lib/libgeos_c.so.1 (0x00007ba738440000) | libgeos.so.3.16.0 => /usr/local/lib/libgeos.so.3.16.0 (0x00007ba736c1b000)`
  - backend 87 maps: ['/usr/local/lib/libgeos_c.so.1.23.0', '/usr/local/lib/libgeos.so.3.16.0']
  - sha256 (runtime): {'/usr/local/lib/libgeos.so.3.16.0': 'c4e372ce9187af33b11dafff5a86ab34c486f2423e09f00651e8a20ac4600687', '/usr/local/lib/libgeos_c.so.1.23.0': '0d673b59a0a8dd27dca9c225fcef951183e0bb526bb4813a47875e0925ddc94a'}
  - sha256 (build record): -
- verify_after: ok=True problems=[]
  - postgis_geos_version: `3.16.0dev-CAPI-1.23.0 3.15.0rc1-41-g283e82726`
  - marker /_tavs_geos_commit.txt: None; base image marker: commit 283e82726fbd5ecc45397f182e12e056a65b2dd7; GEOS version names the commit: None
  - PostGIS library: `/usr/lib/postgresql/18/lib/postgis-3.so`; ldd: `libgeos_c.so.1 => /usr/local/lib/libgeos_c.so.1 (0x00007c71303a9000) | libgeos.so.3.16.0 => /usr/local/lib/libgeos.so.3.16.0 (0x00007c712eb84000)`
  - backend 7638 maps: ['/usr/local/lib/libgeos_c.so.1.23.0', '/usr/local/lib/libgeos.so.3.16.0']
  - sha256 (runtime): {'/usr/local/lib/libgeos.so.3.16.0': 'c4e372ce9187af33b11dafff5a86ab34c486f2423e09f00651e8a20ac4600687', '/usr/local/lib/libgeos_c.so.1.23.0': '0d673b59a0a8dd27dca9c225fcef951183e0bb526bb4813a47875e0925ddc94a'}
  - sha256 (build record): -
- 2026-11-06 15:21:39 -0300 started tavs-e5-dev-13384 from postgis/postgis@sha256:620f1f1ffb479ffbda686dbfde113557a9859cdf9de0f86683b0702846915107 on 127.0.0.1:55621
- 2026-11-06 15:52:22 -0300 removed tavs-e5-dev-13384: rc=0

## postgis_full_version per target

- before: `POSTGIS="3.7.0dev 3.7.0rc3-1-g4db4d8050" [EXTENSION] PGSQL="180" GEOS="3.16.0dev-CAPI-1.23.0 3.15.0rc1-54-gfc3eca906" PROJ="9.10.0 NETWORK_ENABLED=OFF URL_ENDPOINT=https://cdn.proj.org USER_WRITABLE_DIRECTORY=/var/lib/postgresql/.local/share/proj DATABASE_PATH=/usr/local/share/proj/proj.db" (compiled against PROJ 9.10.0) LIBXML="2.9.14" LIBJSON="0.18" LIBPROTOBUF="1.5.1" WAGYU="0.5.0 (Internal)" TOPOLOGY`
- fix: `POSTGIS="3.7.0dev 3.7.0rc3-1-g4db4d8050" [EXTENSION] PGSQL="180" GEOS="3.16.0dev-CAPI-1.23.0 3.15.0rc1-55-g2c8e04faf" PROJ="9.10.0 NETWORK_ENABLED=OFF URL_ENDPOINT=https://cdn.proj.org USER_WRITABLE_DIRECTORY=/var/lib/postgresql/.local/share/proj DATABASE_PATH=/usr/local/share/proj/proj.db" (compiled against PROJ 9.10.0) LIBXML="2.9.14" LIBJSON="0.18" LIBPROTOBUF="1.5.1" WAGYU="0.5.0 (Internal)" TOPOLOGY`
- dev: `POSTGIS="3.7.0dev 3.7.0rc3-1-g4db4d8050" [EXTENSION] PGSQL="180" GEOS="3.16.0dev-CAPI-1.23.0 3.15.0rc1-41-g283e82726" PROJ="9.10.0 NETWORK_ENABLED=OFF URL_ENDPOINT=https://cdn.proj.org USER_WRITABLE_DIRECTORY=/var/lib/postgresql/.local/share/proj DATABASE_PATH=/usr/local/share/proj/proj.db" (compiled against PROJ 9.10.0) LIBXML="2.9.14" LIBJSON="0.18" LIBPROTOBUF="1.5.1" WAGYU="0.5.0 (Internal)" TOPOLOGY`

