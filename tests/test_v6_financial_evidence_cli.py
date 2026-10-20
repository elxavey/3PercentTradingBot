import unittest
from tradepilot.v6_financial_evidence_cli import stage
from tradepilot.v6_financial_source_queue_cli import build

class GenericEvidenceTests(unittest.TestCase):
    def test_arbitrary_issuer_ytd_quarter_and_provenance_gate(self):
        base=dict(symbol="XYZ.MX",metric="operating_cash_flow",fiscal_year="2023",
                  currency="MXN",scale="1000",accounting_basis="IFRS",
                  consolidation="CONSOLIDATED",source_url="https://example.org/a.pdf",
                  source_page="3",published_at="2023-08-01",
                  publication_evidence="ARCHIVE_MONTH_PROXY",verification_status="PENDING_REVIEW")
        q2=dict(base,quarter="2",period_end="2023-06-30",value="800")
        q1=dict(base,quarter="1",period_end="2023-03-31",value="300")
        staged,eligible,audit=stage([], [q1,q2])
        self.assertEqual(len(staged),2)
        self.assertEqual(next(r for r in staged if r["period_end"]=="2023-06-30")["value"],"500.0")
        self.assertFalse(eligible)

    def test_independently_proven_verified_row_is_eligible(self):
        row=dict(symbol="ANY.MX",metric="revenue",period_start="2023-04-01",
                 period_end="2023-06-30",published_at="2023-07-20",
                 value="100",currency="MXN",scale="1000000",
                 source_url="https://issuer.example/2023.pdf",source_page="4",
                 verification_status="VERIFIED",publication_evidence="ISSUER_DATED_RELEASE",
                 accounting_basis="IFRS",consolidation="CONSOLIDATED")
        staged,eligible,audit=stage([row],[])
        self.assertEqual(len(eligible),1)
        self.assertEqual(eligible[0]["symbol"],"ANY.MX")

    def test_unproven_direct_date_is_not_eligible(self):
        row=dict(symbol="ANY.MX",metric="revenue",period_end="2023-06-30",
                 verification_status="VERIFIED",publication_evidence="ARCHIVE_MONTH_PROXY",
                 accounting_basis="IFRS",consolidation="CONSOLIDATED")
        _,eligible,audit=stage([row],[])
        self.assertFalse(eligible)
        self.assertEqual(audit[0]["status"],"PENDING_REVIEW")

    def test_queue_unknown_issuer(self):
        cases=[dict(case_id="1",symbol="NEW.MX",market="MX",signal_date="2023-08-15"),
               dict(case_id="2",symbol="CUSTOM",market="US",signal_date="2023-08-15")]
        queue=build(cases,[])
        self.assertEqual([x["source_status"] for x in queue],["UNKNOWN_SOURCE","SEC_PROVIDER"])

if __name__=="__main__":
    unittest.main()
