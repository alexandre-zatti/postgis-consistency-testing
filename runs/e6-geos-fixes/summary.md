# E6: families B to F replayed on GEOS before and at the fixes (GEOS PR #1601, #1615)

- Command: `python.exe -s -m tavs.replay_fixes`
- Working directory: `C:\Users\Ale\masters\coursework\MCET063 - Tópicos em Testes Automatizados e Verificação de Software (2026-2)\final-project\experiment`
- Start: 2026-11-23 20:18:44 -0300; end: 2026-11-23 20:22:11 -0300
- Repository HEAD: 1e65d145027c6f1aecd641fa4b738f8f3ad2967f; uncommitted changes in tavs/, docker/, scripts/: ?? scripts/run_e6_geos_fixes.ps1; ?? tavs/replay_fixes.py
- Python 3.14.7, Windows-11-10.0.26300-SP0
- Inputs: ['C:\\Users\\Ale\\masters\\coursework\\MCET063 - Tópicos em Testes Automatizados e Verificação de Software (2026-2)\\final-project\\experiment\\runs\\e3\\triage\\families.csv', 'C:\\Users\\Ale\\masters\\coursework\\MCET063 - Tópicos em Testes Automatizados e Verificação de Software (2026-2)\\final-project\\experiment\\runs\\e3\\triage\\findings.json', 'C:\\Users\\Ale\\masters\\coursework\\MCET063 - Tópicos em Testes Automatizados e Verificação de Software (2026-2)\\final-project\\experiment\\findings\\B-prepared-contains-empty-member\\reproduce.sql', 'C:\\Users\\Ale\\masters\\coursework\\MCET063 - Tópicos em Testes Automatizados e Verificação de Software (2026-2)\\final-project\\experiment\\findings\\D-relate-not-symmetric-self-noding\\reproduce.sql']
- Findings: 92 (B 58, C 29, D 2, E 1, F 2); selection: {'families': ['B', 'C', 'D', 'E', 'F'], 'limit': None, 'keys': None}
- Targets: before-b=tavs-geos:before-faaaad0b, fix-b=tavs-geos:fix-695a1909, before-d=tavs-geos:before-b6754aa2, fix-d=tavs-geos:fix-35fa80c9

Expectation fixed before the run: all 58 family B findings reproduce on before-b and none on fix-b, before-d or fix-d; both family D findings reproduce on before-b, fix-b and before-d and none on fix-d. Families C, E and F carry no expectation and are reported as observed.

- Check: `triage.rerun(finding, tw, tdir)` unchanged, with `tw` mapping its three image slots (current, dev, old) to this target's container: three evaluations per finding and target. Status from slot `current`: `reproduces` when `present_counted`; else `crash` when an outcome is `crash`; else `other error` when an outcome kind is outside ['not_applicable', 'skipped', 'tier_mismatch'] or rerun raised; else `not reproduced`.

## Status per family and target

Cells: reproduces / not reproduced / crash / other error, of the family total.

| family | n | before-b | fix-b | before-d | fix-d |
|---|---|---|---|---|---|
| B | 58 | 58 / 0 / 0 / 0 of 58 | 0 / 58 / 0 / 0 of 58 | 0 / 58 / 0 / 0 of 58 | 0 / 58 / 0 / 0 of 58 |
| C | 29 | 29 / 0 / 0 / 0 of 29 | 29 / 0 / 0 / 0 of 29 | 29 / 0 / 0 / 0 of 29 | 24 / 5 / 0 / 0 of 29 |
| D | 2 | 2 / 0 / 0 / 0 of 2 | 2 / 0 / 0 / 0 of 2 | 2 / 0 / 0 / 0 of 2 | 0 / 2 / 0 / 0 of 2 |
| E | 1 | 1 / 0 / 0 / 0 of 1 | 1 / 0 / 0 / 0 of 1 | 1 / 0 / 0 / 0 of 1 | 1 / 0 / 0 / 0 of 1 |
| F | 2 | 2 / 0 / 0 / 0 of 2 | 2 / 0 / 0 / 0 of 2 | 2 / 0 / 0 / 0 of 2 | 2 / 0 / 0 / 0 of 2 |

## Control: before-b against the triage's recorded `dev` result

- B: 58 / 58 agree (of 58)
- C: 29 / 29 agree (of 29)
- D: 2 / 2 agree (of 2)
- E: 1 / 1 agree (of 1)
- F: 2 / 2 agree (of 2)

Disagreements: none.

Repeats within a target (rerun's three slots) disagree: none.

## Deviations from the expectation (families B and D)

none

## Families C, E, F: findings whose status changes between targets

- 49271cf2e457 (C R4 ForceCollection(arg1) / Relate): before-b reproduces, fix-b reproduces, before-d reproduces, fix-d not reproduced
- 5eb8d91024c7 (C R2 Relate transpose / Relate): before-b reproduces, fix-b reproduces, before-d reproduces, fix-d not reproduced
- 674370b598e4 (C R4 ForceCollection(arg1) / Relate): before-b reproduces, fix-b reproduces, before-d reproduces, fix-d not reproduced
- 7d21957b5d7f (C R2 Relate transpose / Relate): before-b reproduces, fix-b reproduces, before-d reproduces, fix-d not reproduced
- 8c2fe870bc29 (C R4 ForceCollection(arg1) / Relate): before-b reproduces, fix-b reproduces, before-d reproduces, fix-d not reproduced

## Reproducers (one statement at a time)

- before-b B: 1=[["3.7.0dev", "3.16.0dev-CAPI-1.23.0"]]; 2=[["FF20F1FF2"]]; 3=[["GC(POINT, POLYGON EMPTY)", [false, true, true]]]; 4=[["GC(POINT, LINESTRING EMPTY)", [false, true, true]]]; 5=[["POINT", [false, false, false]]]
- before-b D: 1=[["3.7.0dev", "3.16.0dev-CAPI-1.23.0"]]; 2=[["212101212", "212111212", "212101212", false]]
- fix-b B: 1=[["3.7.0dev", "3.16.0dev-CAPI-1.23.0"]]; 2=[["FF20F1FF2"]]; 3=[["GC(POINT, POLYGON EMPTY)", [false, false, false]]]; 4=[["GC(POINT, LINESTRING EMPTY)", [false, false, false]]]; 5=[["POINT", [false, false, false]]]
- fix-b D: 1=[["3.7.0dev", "3.16.0dev-CAPI-1.23.0"]]; 2=[["212101212", "212111212", "212101212", false]]
- before-d B: 1=[["3.7.0dev", "3.16.0dev-CAPI-1.23.0"]]; 2=[["FF20F1FF2"]]; 3=[["GC(POINT, POLYGON EMPTY)", [false, false, false]]]; 4=[["GC(POINT, LINESTRING EMPTY)", [false, false, false]]]; 5=[["POINT", [false, false, false]]]
- before-d D: 1=[["3.7.0dev", "3.16.0dev-CAPI-1.23.0"]]; 2=[["212101212", "212111212", "212101212", false]]
- fix-d B: 1=[["3.7.0dev", "3.16.0dev-CAPI-1.23.0"]]; 2=[["FF20F1FF2"]]; 3=[["GC(POINT, POLYGON EMPTY)", [false, false, false]]]; 4=[["GC(POINT, LINESTRING EMPTY)", [false, false, false]]]; 5=[["POINT", [false, false, false]]]
- fix-d D: 1=[["3.7.0dev", "3.16.0dev-CAPI-1.23.0"]]; 2=[["212111212", "212111212", "212111212", true]]

## Targets

### before-b

- Image: `tavs-geos:before-faaaad0b`; id `sha256:f1dfe378b05c8d9a99203405692e11a83618309491b6d7963bcaabb9589a75d2`; digests ['tavs-geos@sha256:f1dfe378b05c8d9a99203405692e11a83618309491b6d7963bcaabb9589a75d2']; created 2026-11-23T23:00:38.497976503Z; label tavs.geos.commit faaaad0b0b95e8a0bdb72e2b28416bd1511e7deb
- Container image id: `sha256:f1dfe378b05c8d9a99203405692e11a83618309491b6d7963bcaabb9589a75d2`
- Expected GEOS commit: faaaad0b0b95e8a0bdb72e2b28416bd1511e7deb
- Start 2026-11-23 20:18:44 -0300, end 2026-11-23 20:19:37 -0300
- docker run: `docker run -d --rm --pull never --name tavs-e6-before-b-7432 --label tavs.e6=1 -e POSTGRES_PASSWORD=postgis --shm-size 256m -p 127.0.0.1:53267:5432 tavs-geos:before-faaaad0b postgres -c fsync=off -c synchronous_commit=off -c full_page_writes=off`
- verify_before: ok=True problems=[]
  - postgis_geos_version: `3.16.0dev-CAPI-1.23.0 3.15.0rc1-68-gfaaaad0b0`
  - marker /_tavs_geos_commit.txt: faaaad0b0b95e8a0bdb72e2b28416bd1511e7deb; base image marker: commit 283e82726fbd5ecc45397f182e12e056a65b2dd7; GEOS version names the commit: True
  - PostGIS library: `/usr/lib/postgresql/18/lib/postgis-3.so`; ldd: `libgeos_c.so.1 => /usr/local/lib/libgeos_c.so.1 (0x0000745273e63000) | libgeos.so.3.16.0 => /usr/local/lib/libgeos.so.3.16.0 (0x000074527263e000)`
  - backend 87 maps: ['/usr/local/lib/libgeos_c.so.1.23.0', '/usr/local/lib/libgeos.so.3.16.0']
  - sha256 (runtime): {'/usr/local/lib/libgeos.so.3.16.0': '89cfb66d6f81330030dcc025b9cf6e810ad2d6afcee3fd4173aa2351a1bc1636', '/usr/local/lib/libgeos_c.so.1.23.0': 'f8767ad70884b85684b8953a5bce3e0b17dec1a959b0bd6f0bcbf94062d8eb8b'}
  - sha256 (build record): {'libgeos_c.so.1.23.0': 'f8767ad70884b85684b8953a5bce3e0b17dec1a959b0bd6f0bcbf94062d8eb8b', 'libgeos.so.3.16.0': '89cfb66d6f81330030dcc025b9cf6e810ad2d6afcee3fd4173aa2351a1bc1636'}
  - build record /_tavs_geos_build.txt:

```
GEOS_COMMIT=faaaad0b0b95e8a0bdb72e2b28416bd1511e7deb
git describe: 3.15.0rc1-68-gfaaaad0b0
commit faaaad0b0b95e8a0bdb72e2b28416bd1511e7deb
Author: Daniel Baston <dbaston@gmail.com>
Date:   Thu Nov 19 12:01:09 2026 -0500

    IsSimpleOp: add test
cmake: -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DCMAKE_INSTALL_PREFIX=/usr/local -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=OFF; make -j6
compiler: g++ (Debian 14.2.0-19) 14.2.0
sha256 of the built libraries:
f8767ad70884b85684b8953a5bce3e0b17dec1a959b0bd6f0bcbf94062d8eb8b  libgeos_c.so.1.23.0
89cfb66d6f81330030dcc025b9cf6e810ad2d6afcee3fd4173aa2351a1bc1636  libgeos.so.3.16.0
```

- verify_after: ok=True problems=[]
  - postgis_geos_version: `3.16.0dev-CAPI-1.23.0 3.15.0rc1-68-gfaaaad0b0`
  - marker /_tavs_geos_commit.txt: faaaad0b0b95e8a0bdb72e2b28416bd1511e7deb; base image marker: commit 283e82726fbd5ecc45397f182e12e056a65b2dd7; GEOS version names the commit: True
  - PostGIS library: `/usr/lib/postgresql/18/lib/postgis-3.so`; ldd: `libgeos_c.so.1 => /usr/local/lib/libgeos_c.so.1 (0x0000769af9762000) | libgeos.so.3.16.0 => /usr/local/lib/libgeos.so.3.16.0 (0x0000769af7f3d000)`
  - backend 150 maps: ['/usr/local/lib/libgeos_c.so.1.23.0', '/usr/local/lib/libgeos.so.3.16.0']
  - sha256 (runtime): {'/usr/local/lib/libgeos.so.3.16.0': '89cfb66d6f81330030dcc025b9cf6e810ad2d6afcee3fd4173aa2351a1bc1636', '/usr/local/lib/libgeos_c.so.1.23.0': 'f8767ad70884b85684b8953a5bce3e0b17dec1a959b0bd6f0bcbf94062d8eb8b'}
  - sha256 (build record): {'libgeos_c.so.1.23.0': 'f8767ad70884b85684b8953a5bce3e0b17dec1a959b0bd6f0bcbf94062d8eb8b', 'libgeos.so.3.16.0': '89cfb66d6f81330030dcc025b9cf6e810ad2d6afcee3fd4173aa2351a1bc1636'}
- 2026-11-23 20:18:44 -0300 started tavs-e6-before-b-7432 from tavs-geos:before-faaaad0b on 127.0.0.1:53267
- 2026-11-23 20:19:37 -0300 removed tavs-e6-before-b-7432: rc=0

### fix-b

- Image: `tavs-geos:fix-695a1909`; id `sha256:7cbbfd80062c7b0755ba2066c40d607cefd38647ad84e349b01f1e2e21604d2b`; digests ['tavs-geos@sha256:7cbbfd80062c7b0755ba2066c40d607cefd38647ad84e349b01f1e2e21604d2b']; created 2026-11-23T23:14:10.997948808Z; label tavs.geos.commit 695a19097e4750e689c02f6b4de69bc25a5f70e3
- Container image id: `sha256:7cbbfd80062c7b0755ba2066c40d607cefd38647ad84e349b01f1e2e21604d2b`
- Expected GEOS commit: 695a19097e4750e689c02f6b4de69bc25a5f70e3
- Start 2026-11-23 20:19:37 -0300, end 2026-11-23 20:20:28 -0300
- docker run: `docker run -d --rm --pull never --name tavs-e6-fix-b-7432 --label tavs.e6=1 -e POSTGRES_PASSWORD=postgis --shm-size 256m -p 127.0.0.1:53280:5432 tavs-geos:fix-695a1909 postgres -c fsync=off -c synchronous_commit=off -c full_page_writes=off`
- verify_before: ok=True problems=[]
  - postgis_geos_version: `3.16.0dev-CAPI-1.23.0 3.15.0rc1-69-g695a19097`
  - marker /_tavs_geos_commit.txt: 695a19097e4750e689c02f6b4de69bc25a5f70e3; base image marker: commit 283e82726fbd5ecc45397f182e12e056a65b2dd7; GEOS version names the commit: True
  - PostGIS library: `/usr/lib/postgresql/18/lib/postgis-3.so`; ldd: `libgeos_c.so.1 => /usr/local/lib/libgeos_c.so.1 (0x00007f4e0d934000) | libgeos.so.3.16.0 => /usr/local/lib/libgeos.so.3.16.0 (0x00007f4e0c10f000)`
  - backend 87 maps: ['/usr/local/lib/libgeos_c.so.1.23.0', '/usr/local/lib/libgeos.so.3.16.0']
  - sha256 (runtime): {'/usr/local/lib/libgeos.so.3.16.0': '3e9b7b2fa22ba58f5e017acffc7916328e9bc44d54283562a3b78fc5ea3cf2fe', '/usr/local/lib/libgeos_c.so.1.23.0': '73e4e8193f4fe64b34376d301d54b3e492f20688cf672b506e62f907daafebf8'}
  - sha256 (build record): {'libgeos_c.so.1.23.0': '73e4e8193f4fe64b34376d301d54b3e492f20688cf672b506e62f907daafebf8', 'libgeos.so.3.16.0': '3e9b7b2fa22ba58f5e017acffc7916328e9bc44d54283562a3b78fc5ea3cf2fe'}
  - build record /_tavs_geos_build.txt:

```
GEOS_COMMIT=695a19097e4750e689c02f6b4de69bc25a5f70e3
git describe: 3.15.0rc1-69-g695a19097
commit 695a19097e4750e689c02f6b4de69bc25a5f70e3
Author: Daniel Baston <dbaston@gmail.com>
Date:   Thu Nov 19 18:44:23 2026 -0500

    PreparedPolygonContains: Resolve errors with on collections with mixed dims or empty components (#1601)
    
    Resolves https://github.com/libgeos/geos/issues/1599
cmake: -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DCMAKE_INSTALL_PREFIX=/usr/local -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=OFF; make -j6
compiler: g++ (Debian 14.2.0-19) 14.2.0
sha256 of the built libraries:
73e4e8193f4fe64b34376d301d54b3e492f20688cf672b506e62f907daafebf8  libgeos_c.so.1.23.0
3e9b7b2fa22ba58f5e017acffc7916328e9bc44d54283562a3b78fc5ea3cf2fe  libgeos.so.3.16.0
```

- verify_after: ok=True problems=[]
  - postgis_geos_version: `3.16.0dev-CAPI-1.23.0 3.15.0rc1-69-g695a19097`
  - marker /_tavs_geos_commit.txt: 695a19097e4750e689c02f6b4de69bc25a5f70e3; base image marker: commit 283e82726fbd5ecc45397f182e12e056a65b2dd7; GEOS version names the commit: True
  - PostGIS library: `/usr/lib/postgresql/18/lib/postgis-3.so`; ldd: `libgeos_c.so.1 => /usr/local/lib/libgeos_c.so.1 (0x00007ae161ddb000) | libgeos.so.3.16.0 => /usr/local/lib/libgeos.so.3.16.0 (0x00007ae1605b6000)`
  - backend 152 maps: ['/usr/local/lib/libgeos_c.so.1.23.0', '/usr/local/lib/libgeos.so.3.16.0']
  - sha256 (runtime): {'/usr/local/lib/libgeos.so.3.16.0': '3e9b7b2fa22ba58f5e017acffc7916328e9bc44d54283562a3b78fc5ea3cf2fe', '/usr/local/lib/libgeos_c.so.1.23.0': '73e4e8193f4fe64b34376d301d54b3e492f20688cf672b506e62f907daafebf8'}
  - sha256 (build record): {'libgeos_c.so.1.23.0': '73e4e8193f4fe64b34376d301d54b3e492f20688cf672b506e62f907daafebf8', 'libgeos.so.3.16.0': '3e9b7b2fa22ba58f5e017acffc7916328e9bc44d54283562a3b78fc5ea3cf2fe'}
- 2026-11-23 20:19:37 -0300 started tavs-e6-fix-b-7432 from tavs-geos:fix-695a1909 on 127.0.0.1:53280
- 2026-11-23 20:20:28 -0300 removed tavs-e6-fix-b-7432: rc=0

### before-d

- Image: `tavs-geos:before-b6754aa2`; id `sha256:c1fd867fe0dc26e903d65a730222b07f105900dc24db3445c4a06c07eb2f0843`; digests ['tavs-geos@sha256:c1fd867fe0dc26e903d65a730222b07f105900dc24db3445c4a06c07eb2f0843']; created 2026-11-23T23:16:12.88093013Z; label tavs.geos.commit b6754aa2eb591a2bdabfe7f730c1e3c9c71408e5
- Container image id: `sha256:c1fd867fe0dc26e903d65a730222b07f105900dc24db3445c4a06c07eb2f0843`
- Expected GEOS commit: b6754aa2eb591a2bdabfe7f730c1e3c9c71408e5
- Start 2026-11-23 20:20:28 -0300, end 2026-11-23 20:21:20 -0300
- docker run: `docker run -d --rm --pull never --name tavs-e6-before-d-7432 --label tavs.e6=1 -e POSTGRES_PASSWORD=postgis --shm-size 256m -p 127.0.0.1:53290:5432 tavs-geos:before-b6754aa2 postgres -c fsync=off -c synchronous_commit=off -c full_page_writes=off`
- verify_before: ok=True problems=[]
  - postgis_geos_version: `3.16.0dev-CAPI-1.23.0 3.15.0rc1-70-gb6754aa2e`
  - marker /_tavs_geos_commit.txt: b6754aa2eb591a2bdabfe7f730c1e3c9c71408e5; base image marker: commit 283e82726fbd5ecc45397f182e12e056a65b2dd7; GEOS version names the commit: True
  - PostGIS library: `/usr/lib/postgresql/18/lib/postgis-3.so`; ldd: `libgeos_c.so.1 => /usr/local/lib/libgeos_c.so.1 (0x00007b7b3795b000) | libgeos.so.3.16.0 => /usr/local/lib/libgeos.so.3.16.0 (0x00007b7b36136000)`
  - backend 87 maps: ['/usr/local/lib/libgeos_c.so.1.23.0', '/usr/local/lib/libgeos.so.3.16.0']
  - sha256 (runtime): {'/usr/local/lib/libgeos.so.3.16.0': '434276eff623f08eea796ad2fb049617a2c07b80a39dd153dd717b7217b8b71a', '/usr/local/lib/libgeos_c.so.1.23.0': '972454f6023761cfc7e84f074bd3ec07f0be35f6825fa48c7e58378e0dec4d2c'}
  - sha256 (build record): {'libgeos_c.so.1.23.0': '972454f6023761cfc7e84f074bd3ec07f0be35f6825fa48c7e58378e0dec4d2c', 'libgeos.so.3.16.0': '434276eff623f08eea796ad2fb049617a2c07b80a39dd153dd717b7217b8b71a'}
  - build record /_tavs_geos_build.txt:

```
GEOS_COMMIT=b6754aa2eb591a2bdabfe7f730c1e3c9c71408e5
git describe: 3.15.0rc1-70-gb6754aa2e
commit b6754aa2eb591a2bdabfe7f730c1e3c9c71408e5
Author: Daniel Baston <dbaston@gmail.com>
Date:   Thu Nov 19 20:04:47 2026 -0500

    RectangleContains: guard against curved inputs (#1617)
cmake: -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DCMAKE_INSTALL_PREFIX=/usr/local -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=OFF; make -j6
compiler: g++ (Debian 14.2.0-19) 14.2.0
sha256 of the built libraries:
972454f6023761cfc7e84f074bd3ec07f0be35f6825fa48c7e58378e0dec4d2c  libgeos_c.so.1.23.0
434276eff623f08eea796ad2fb049617a2c07b80a39dd153dd717b7217b8b71a  libgeos.so.3.16.0
```

- verify_after: ok=True problems=[]
  - postgis_geos_version: `3.16.0dev-CAPI-1.23.0 3.15.0rc1-70-gb6754aa2e`
  - marker /_tavs_geos_commit.txt: b6754aa2eb591a2bdabfe7f730c1e3c9c71408e5; base image marker: commit 283e82726fbd5ecc45397f182e12e056a65b2dd7; GEOS version names the commit: True
  - PostGIS library: `/usr/lib/postgresql/18/lib/postgis-3.so`; ldd: `libgeos_c.so.1 => /usr/local/lib/libgeos_c.so.1 (0x000076526afd4000) | libgeos.so.3.16.0 => /usr/local/lib/libgeos.so.3.16.0 (0x00007652697af000)`
  - backend 153 maps: ['/usr/local/lib/libgeos_c.so.1.23.0', '/usr/local/lib/libgeos.so.3.16.0']
  - sha256 (runtime): {'/usr/local/lib/libgeos.so.3.16.0': '434276eff623f08eea796ad2fb049617a2c07b80a39dd153dd717b7217b8b71a', '/usr/local/lib/libgeos_c.so.1.23.0': '972454f6023761cfc7e84f074bd3ec07f0be35f6825fa48c7e58378e0dec4d2c'}
  - sha256 (build record): {'libgeos_c.so.1.23.0': '972454f6023761cfc7e84f074bd3ec07f0be35f6825fa48c7e58378e0dec4d2c', 'libgeos.so.3.16.0': '434276eff623f08eea796ad2fb049617a2c07b80a39dd153dd717b7217b8b71a'}
- 2026-11-23 20:20:29 -0300 started tavs-e6-before-d-7432 from tavs-geos:before-b6754aa2 on 127.0.0.1:53290
- 2026-11-23 20:21:20 -0300 removed tavs-e6-before-d-7432: rc=0

### fix-d

- Image: `tavs-geos:fix-35fa80c9`; id `sha256:0edc3aead97a0c671456b58245d529b0b7c212c89b5e6c0a9196cc132cb73a0f`; digests ['tavs-geos@sha256:0edc3aead97a0c671456b58245d529b0b7c212c89b5e6c0a9196cc132cb73a0f']; created 2026-11-23T23:18:15.43818712Z; label tavs.geos.commit 35fa80c99e8db5738f06163082caa49fc7c2ee3d
- Container image id: `sha256:0edc3aead97a0c671456b58245d529b0b7c212c89b5e6c0a9196cc132cb73a0f`
- Expected GEOS commit: 35fa80c99e8db5738f06163082caa49fc7c2ee3d
- Start 2026-11-23 20:21:20 -0300, end 2026-11-23 20:22:11 -0300
- docker run: `docker run -d --rm --pull never --name tavs-e6-fix-d-7432 --label tavs.e6=1 -e POSTGRES_PASSWORD=postgis --shm-size 256m -p 127.0.0.1:53300:5432 tavs-geos:fix-35fa80c9 postgres -c fsync=off -c synchronous_commit=off -c full_page_writes=off`
- verify_before: ok=True problems=[]
  - postgis_geos_version: `3.16.0dev-CAPI-1.23.0 3.15.0rc1-71-g35fa80c99`
  - marker /_tavs_geos_commit.txt: 35fa80c99e8db5738f06163082caa49fc7c2ee3d; base image marker: commit 283e82726fbd5ecc45397f182e12e056a65b2dd7; GEOS version names the commit: True
  - PostGIS library: `/usr/lib/postgresql/18/lib/postgis-3.so`; ldd: `libgeos_c.so.1 => /usr/local/lib/libgeos_c.so.1 (0x000073dc484d4000) | libgeos.so.3.16.0 => /usr/local/lib/libgeos.so.3.16.0 (0x000073dc46caf000)`
  - backend 87 maps: ['/usr/local/lib/libgeos_c.so.1.23.0', '/usr/local/lib/libgeos.so.3.16.0']
  - sha256 (runtime): {'/usr/local/lib/libgeos.so.3.16.0': '11c813f54e6362410268d92f772d3b722275b4f2671cea47c0d7d9bb2f1955e9', '/usr/local/lib/libgeos_c.so.1.23.0': '0443b2bea9f32db6b3af967eff6cc9a3e8413f0f2d9feb17f912b91a3e99ccbb'}
  - sha256 (build record): {'libgeos_c.so.1.23.0': '0443b2bea9f32db6b3af967eff6cc9a3e8413f0f2d9feb17f912b91a3e99ccbb', 'libgeos.so.3.16.0': '11c813f54e6362410268d92f772d3b722275b4f2671cea47c0d7d9bb2f1955e9'}
  - build record /_tavs_geos_build.txt:

```
GEOS_COMMIT=35fa80c99e8db5738f06163082caa49fc7c2ee3d
git describe: 3.15.0rc1-71-g35fa80c99
commit 35fa80c99e8db5738f06163082caa49fc7c2ee3d
Author: Daniel Baston <dbaston@gmail.com>
Date:   Thu Nov 19 20:05:31 2026 -0500

    RelateNG: Fix strategy for self-noding (#1615)
    
    Based on https://github.com/locationtech/jts/pull/1259 and https://github.com/locationtech/jts/pull/1260
    
    Fixes https://github.com/libgeos/geos/issues/1558
    Fixes https://github.com/libgeos/geos/issues/1595
    Fixes https://github.com/libgeos/geos/issues/1597
    
    Co-authored-by: Martin Davis <mtnclimb@gmail.com>
cmake: -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DCMAKE_INSTALL_PREFIX=/usr/local -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=OFF; make -j6
compiler: g++ (Debian 14.2.0-19) 14.2.0
sha256 of the built libraries:
0443b2bea9f32db6b3af967eff6cc9a3e8413f0f2d9feb17f912b91a3e99ccbb  libgeos_c.so.1.23.0
11c813f54e6362410268d92f772d3b722275b4f2671cea47c0d7d9bb2f1955e9  libgeos.so.3.16.0
```

- verify_after: ok=True problems=[]
  - postgis_geos_version: `3.16.0dev-CAPI-1.23.0 3.15.0rc1-71-g35fa80c99`
  - marker /_tavs_geos_commit.txt: 35fa80c99e8db5738f06163082caa49fc7c2ee3d; base image marker: commit 283e82726fbd5ecc45397f182e12e056a65b2dd7; GEOS version names the commit: True
  - PostGIS library: `/usr/lib/postgresql/18/lib/postgis-3.so`; ldd: `libgeos_c.so.1 => /usr/local/lib/libgeos_c.so.1 (0x00007330672dc000) | libgeos.so.3.16.0 => /usr/local/lib/libgeos.so.3.16.0 (0x0000733065ab7000)`
  - backend 150 maps: ['/usr/local/lib/libgeos_c.so.1.23.0', '/usr/local/lib/libgeos.so.3.16.0']
  - sha256 (runtime): {'/usr/local/lib/libgeos.so.3.16.0': '11c813f54e6362410268d92f772d3b722275b4f2671cea47c0d7d9bb2f1955e9', '/usr/local/lib/libgeos_c.so.1.23.0': '0443b2bea9f32db6b3af967eff6cc9a3e8413f0f2d9feb17f912b91a3e99ccbb'}
  - sha256 (build record): {'libgeos_c.so.1.23.0': '0443b2bea9f32db6b3af967eff6cc9a3e8413f0f2d9feb17f912b91a3e99ccbb', 'libgeos.so.3.16.0': '11c813f54e6362410268d92f772d3b722275b4f2671cea47c0d7d9bb2f1955e9'}
- 2026-11-23 20:21:20 -0300 started tavs-e6-fix-d-7432 from tavs-geos:fix-35fa80c9 on 127.0.0.1:53300
- 2026-11-23 20:22:11 -0300 removed tavs-e6-fix-d-7432: rc=0

## postgis_full_version per target

- before-b: `POSTGIS="3.7.0dev 3.7.0rc3-1-g4db4d8050" [EXTENSION] PGSQL="180" GEOS="3.16.0dev-CAPI-1.23.0 3.15.0rc1-68-gfaaaad0b0" PROJ="9.10.0 NETWORK_ENABLED=OFF URL_ENDPOINT=https://cdn.proj.org USER_WRITABLE_DIRECTORY=/var/lib/postgresql/.local/share/proj DATABASE_PATH=/usr/local/share/proj/proj.db" (compiled against PROJ 9.10.0) LIBXML="2.9.14" LIBJSON="0.18" LIBPROTOBUF="1.5.1" WAGYU="0.5.0 (Internal)" TOPOLOGY`
- fix-b: `POSTGIS="3.7.0dev 3.7.0rc3-1-g4db4d8050" [EXTENSION] PGSQL="180" GEOS="3.16.0dev-CAPI-1.23.0 3.15.0rc1-69-g695a19097" PROJ="9.10.0 NETWORK_ENABLED=OFF URL_ENDPOINT=https://cdn.proj.org USER_WRITABLE_DIRECTORY=/var/lib/postgresql/.local/share/proj DATABASE_PATH=/usr/local/share/proj/proj.db" (compiled against PROJ 9.10.0) LIBXML="2.9.14" LIBJSON="0.18" LIBPROTOBUF="1.5.1" WAGYU="0.5.0 (Internal)" TOPOLOGY`
- before-d: `POSTGIS="3.7.0dev 3.7.0rc3-1-g4db4d8050" [EXTENSION] PGSQL="180" GEOS="3.16.0dev-CAPI-1.23.0 3.15.0rc1-70-gb6754aa2e" PROJ="9.10.0 NETWORK_ENABLED=OFF URL_ENDPOINT=https://cdn.proj.org USER_WRITABLE_DIRECTORY=/var/lib/postgresql/.local/share/proj DATABASE_PATH=/usr/local/share/proj/proj.db" (compiled against PROJ 9.10.0) LIBXML="2.9.14" LIBJSON="0.18" LIBPROTOBUF="1.5.1" WAGYU="0.5.0 (Internal)" TOPOLOGY`
- fix-d: `POSTGIS="3.7.0dev 3.7.0rc3-1-g4db4d8050" [EXTENSION] PGSQL="180" GEOS="3.16.0dev-CAPI-1.23.0 3.15.0rc1-71-g35fa80c99" PROJ="9.10.0 NETWORK_ENABLED=OFF URL_ENDPOINT=https://cdn.proj.org USER_WRITABLE_DIRECTORY=/var/lib/postgresql/.local/share/proj DATABASE_PATH=/usr/local/share/proj/proj.db" (compiled against PROJ 9.10.0) LIBXML="2.9.14" LIBJSON="0.18" LIBPROTOBUF="1.5.1" WAGYU="0.5.0 (Internal)" TOPOLOGY`

