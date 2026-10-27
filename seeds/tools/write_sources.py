import hashlib, json, os, re, sys
seeds = sys.argv[1]; sha = sys.argv[2]
blobs = dict(l.rstrip("\n").split("\t") for l in open(os.path.join(seeds, "raw", "xml_blobs.tsv"), encoding="utf-8"))
paths = [l.strip() for l in open(os.path.join(seeds, "raw", "xmllist.txt"), encoding="utf-8") if l.strip()]
files = []; total = 0
for p in paths:
    data = open(os.path.join(seeds, "geos-xml", p), "rb").read()
    gitsha = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
    n = len(re.findall(rb"<case\b", data))
    total += n
    files.append({"path": p, "cases": n, "bytes": len(data), "git_blob_sha": gitsha, "blob_matches_tree": gitsha == blobs.get(p)})
out = {
    "geos_xml_tests": {
        "repository": "https://github.com/libgeos/geos",
        "ref": "main", "commit": sha, "commit_date": "2026-10-26T20:07:40Z", "retrieved": "2026-10-27",
        "url_template": "https://raw.githubusercontent.com/libgeos/geos/%s/{path}" % sha,
        "local_root": "seeds/geos-xml/",
        "selection": ["tests/xmltester/tests/validate/TestRelate*.xml", "tests/xmltester/tests/general/TestRelate*.xml",
                      "tests/xmltester/tests/general/TestPrepared*.xml", "tests/xmltester/tests/general/TestOverlay*.xml",
                      "tests/xmltester/tests/general/TestNGOverlay*.xml"],
        "excluded": ["tests/xmltester/tests/general/TestOverlayCurvesAA.xml", "tests/xmltester/tests/general/TestOverlayCurvesLA.xml"],
        "exclusion_rule": "file name contains 'Curve' or 'curve'",
        "case_count_method": "occurrences of '<case' (regex <case\b) per file",
        "license": "LGPL-2.1 (GNU Lesser General Public License v2.1; COPYING at the same commit)",
        "file_count": len(files), "total_cases": total, "files": files},
    "known_bugs_sources": {
        "github_issues": "fetched with gh api (repos/{owner}/{repo}/issues/N and /comments) on 2026-10-27; raw JSON in seeds/raw/",
        "postgis_trac_5938": "https://trac.osgeo.org/postgis/ticket/5938 returned an anti-bot page (raw/trac5938.html); used PostGIS GitHub mirror commits a4886d8581d307a132ac19a3f7c5052e6de65657 and 74d24bc78383f8e021cd6300b5aec1d7278b5487 (raw/pg5938_commits.txt) and stable-3.5 NEWS",
        "geos_1558": "issue deleted (API 404); comments still returned by the comments API (raw/geos_1558_c.json); reproducer from PR #1565 RelateNGTest test<65> (raw/pr1565_test.patch)",
        "geos_1540": "complete EWKB hex for A from GEOS #1530 comment by strk (raw/geos_1530_c.json); JTS #1237 prints a truncated A",
        "geos_news": "raw/NEWS.md from libgeos/geos main, used for fixed_in"}}
json.dump(out, open(os.path.join(seeds, "sources.json"), "w", encoding="utf-8"), indent=2)
print(len(files), total, all(f["blob_matches_tree"] for f in files))
for f in files: print(f["cases"], f["path"])
