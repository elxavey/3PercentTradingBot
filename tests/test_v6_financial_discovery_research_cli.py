import unittest

from tradepilot.v6_financial_discovery_cli import discover,extract_links,trusted_archive_link
from tradepilot.v6_financial_filter_research_cli import evaluate

class DiscoveryResearchTests(unittest.TestCase):
    def test_archive_links_same_host_only_and_no_date_inference(self):
        archive="https://reports.example.com/investors/2023"
        html='<a href="/files/q2_2023.pdf">Q2</a><a href="https://evil.example/q2_2023.pdf">bad</a><a href="/files/readme.txt">text</a>'
        self.assertEqual(extract_links(archive,html),["https://reports.example.com/files/q2_2023.pdf"])
        queue=[dict(case_id="X",symbol="SAMPLE.MX",market="MX",signal_date="2023-08-15",
                    official_archive=archive,initial_document="")]
        docs,errors=discover(queue,fetcher=lambda url:html)
        self.assertEqual(len(docs),1)
        self.assertFalse(errors)
        self.assertEqual(docs[0]["publication_status"],"UNKNOWN")
        self.assertEqual(docs[0]["verification_status"],"PENDING_REVIEW")

    def test_archive_fetch_cached_for_multiple_cases(self):
        calls=[]
        def fetch(url):
            calls.append(url)
            return '<a href="report.pdf">PDF</a>'
        q=[dict(case_id=str(i),symbol="SAMPLE.MX",market="MX",signal_date="2023-08-15",
                official_archive="https://example.org/archive",initial_document="") for i in range(3)]
        docs,errors=discover(q,fetcher=fetch)
        self.assertEqual(len(calls),1)
        self.assertEqual(len(docs),3)

    def test_reject_cross_host(self):
        self.assertFalse(trusted_archive_link("https://issuer.example/reports",
                                               "https://issuer.example.evil.org/a.pdf"))

    def test_retrospective_missing_score_policy(self):
        cases=[dict(case_id="1",symbol="AAA",market="US",signal_date="2023-08-15",
                    fixed_outcome="STOP",fixed_net_pct="-3"),
               dict(case_id="2",symbol="BBB",market="MX",signal_date="2023-08-15",
                    fixed_outcome="TARGET",fixed_net_pct="3")]
        quality=[dict(case_id="1",symbol="AAA",market="US",signal_date="2023-08-15",
                      quality_status="EXPERIMENTAL_COMPLETE",quality_score="35",coverage_pct="100"),
                 dict(case_id="2",symbol="BBB",market="MX",signal_date="2023-08-15",
                      quality_status="INSUFFICIENT_COVERAGE",quality_score="",coverage_pct="0")]
        rows,summary=evaluate(cases,quality,thresholds=(50,))
        retain=next(r for r in rows if r["missing_policy"]=="RETAIN")
        abstain=next(r for r in rows if r["missing_policy"]=="ABSTAIN")
        self.assertEqual((retain["retained"],retain["excluded_stop"]),(1,1))
        self.assertEqual((abstain["retained"],abstain["excluded_target"]),(0,1))
        self.assertEqual(summary["scored"],1)
        self.assertEqual(retain["eligible_for_inference"],"NO_CASE_CONTROL_SAMPLE")

    def test_identity_mismatch_blocks_research(self):
        cases=[dict(case_id="1",symbol="AAA",market="US",signal_date="2023-08-15",
                    fixed_outcome="STOP",fixed_net_pct="-3")]
        quality=[dict(case_id="1",symbol="BBB",market="US",signal_date="2023-08-15",
                      quality_status="EXPERIMENTAL_COMPLETE",quality_score="50",coverage_pct="100")]
        with self.assertRaisesRegex(ValueError,"identity mismatch"):
            evaluate(cases,quality)

if __name__=="__main__":
    unittest.main()
