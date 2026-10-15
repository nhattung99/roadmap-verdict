# v0.2.16
# {
#   "Seq": [
#     { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
#   ]
# }
import json
from dataclasses import dataclass
from genlayer import *


def _addr_str(a: Address) -> str:
    try:
        return a.as_hex
    except Exception:
        return str(a)


def _to_address(val) -> Address:
    if isinstance(val, Address):
        return val
    if isinstance(val, str):
        val_str = val.strip()
        if not val_str.startswith("0x"):
            val_str = "0x" + val_str
        return Address(val_str)
    return Address(val)


def _is_http_url(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")


def _as_int(val, default: int = 0) -> int:
    try:
        return int(val)
    except Exception:
        return default


_VERDICTS = ["DELIVERED", "PARTIALLY_DELIVERED", "NOT_DELIVERED", "UNVERIFIABLE"]
_FILTERS = [
    "",
    "PENDING",
    "DELIVERED",
    "PARTIALLY_DELIVERED",
    "NOT_DELIVERED",
    "UNVERIFIABLE",
]


@allow_storage
@dataclass
class MilestoneReport:
    submitter: Address
    project_name: str
    milestone_description: str
    claimed_completion_date: str
    evidence_urls: DynArray[str]
    status: str
    verdict: str
    confidence: u256
    reasoning: str
    delivered_items: str
    gaps: str
    gap_count: u256
    sources_readable: u256


class RoadmapVerdict(gl.Contract):
    reports: TreeMap[str, MilestoneReport]
    next_id: bigint
    owner: Address

    def __init__(self):
        self.owner = _to_address(gl.message.sender_address)
        self.next_id = bigint(1)

    def _report_dict(self, report_id: str, report: MilestoneReport) -> dict:
        urls = []
        for i in range(len(report.evidence_urls)):
            urls.append(str(report.evidence_urls[i]))
        return {
            "report_id": report_id,
            "submitter": _addr_str(report.submitter),
            "project_name": report.project_name,
            "milestone_description": report.milestone_description,
            "claimed_completion_date": report.claimed_completion_date,
            "evidence_urls": urls,
            "status": report.status,
            "verdict": report.verdict,
            "confidence": _as_int(report.confidence),
            "reasoning": report.reasoning,
            "delivered_items": report.delivered_items,
            "gaps": report.gaps,
            "gap_count": _as_int(report.gap_count),
            "sources_readable": _as_int(report.sources_readable),
        }

    @gl.public.write
    def submit_milestone(
        self,
        project_name: str,
        milestone_description: str,
        claimed_completion_date: str,
        evidence_urls: DynArray[str],
    ) -> str:
        if not project_name or len(project_name.strip()) == 0:
            raise gl.vm.UserError("project_name cannot be empty")
        if len(project_name) > 100:
            raise gl.vm.UserError("project_name cannot exceed 100 characters")

        if not milestone_description or len(milestone_description.strip()) == 0:
            raise gl.vm.UserError("milestone_description cannot be empty")
        if len(milestone_description) > 500:
            raise gl.vm.UserError("milestone_description cannot exceed 500 characters")

        if not claimed_completion_date or len(claimed_completion_date.strip()) == 0:
            raise gl.vm.UserError("claimed_completion_date cannot be empty")
        if len(claimed_completion_date) > 30:
            raise gl.vm.UserError("claimed_completion_date cannot exceed 30 characters")

        num_urls = len(evidence_urls)
        if num_urls < 2:
            raise gl.vm.UserError("At least 2 evidence URLs required")
        if num_urls > 5:
            raise gl.vm.UserError("Maximum 5 evidence URLs")

        urls = []
        for i in range(num_urls):
            url = evidence_urls[i]
            if not isinstance(url, str):
                url = str(url)
            if not _is_http_url(url):
                raise gl.vm.UserError("Invalid URL")
            if url in urls:
                raise gl.vm.UserError("Duplicate evidence URL")
            urls.append(url)

        report_id = str(self.next_id)
        self.next_id += bigint(1)

        report = MilestoneReport(
            submitter=_to_address(gl.message.sender_address),
            project_name=project_name,
            milestone_description=milestone_description,
            claimed_completion_date=claimed_completion_date,
            evidence_urls=urls,
            status="PENDING",
            verdict="",
            confidence=u256(0),
            reasoning="",
            delivered_items="[]",
            gaps="[]",
            gap_count=u256(0),
            sources_readable=u256(0),
        )
        self.reports[report_id] = report
        return report_id

    @gl.public.write
    def verify_milestone(self, report_id: str) -> None:
        if report_id not in self.reports:
            raise gl.vm.UserError("Report not found")

        report = self.reports[report_id]
        if report.status != "PENDING":
            raise gl.vm.UserError("not PENDING")

        evidence_urls_list = []
        for i in range(len(report.evidence_urls)):
            evidence_urls_list.append(str(report.evidence_urls[i]))
        project_name_cap = report.project_name
        milestone_desc_cap = report.milestone_description
        completion_date_cap = report.claimed_completion_date

        def leader_fn():
            readable_count = 0
            try:
                evidence_results = []
                for url in evidence_urls_list:
                    try:
                        res = gl.nondet.web.render(url)
                        body = res.body if hasattr(res, "body") else str(res)
                        if not isinstance(body, str):
                            body = str(body)
                        if body and len(body.strip()) > 30:
                            evidence_results.append(
                                "Evidence [" + url + "]:\n" + body[:3000]
                            )
                            readable_count += 1
                        else:
                            evidence_results.append(
                                "Evidence [" + url + "]: (empty or too short)"
                            )
                    except Exception as e:
                        evidence_results.append(
                            "Evidence [" + url + "]: (fetch failed: " + str(e) + ")"
                        )

                prompt = f"""You are an expert Web3 project milestone verification analyst on GenLayer. Your job is to determine whether a Web3 project actually delivered a promised roadmap milestone based on public evidence.

Project Name: {project_name_cap}
Milestone Promised: "{milestone_desc_cap}"
Claimed Completion Date: {completion_date_cap}

Public evidence URLs fetched on-chain:
{chr(10).join(evidence_results)}

Verification instructions:
1. Read each piece of evidence carefully.
2. Identify what specific deliverables from the milestone description are confirmed by the evidence (delivered_items).
3. Identify what specific deliverables from the milestone description are missing or only partially present (gaps).
4. Assess timing: does the evidence suggest delivery happened by the claimed completion date or after?

Verdict options:
- "DELIVERED": All major deliverables in the milestone description are confirmed by at least one readable evidence source. Timing is approximately correct (within 30 days of claimed date).
- "PARTIALLY_DELIVERED": Some deliverables are confirmed but others are clearly missing or not evidenced. Or delivery happened significantly late (more than 30 days after claimed date).
- "NOT_DELIVERED": No meaningful delivery evidence found, or evidence clearly contradicts the milestone claim.
- "UNVERIFIABLE": Fewer than 2 evidence URLs returned readable content. Cannot make a determination.

For delivered_items: list each confirmed deliverable as a string.
For gaps: list each missing or incomplete deliverable as a string.
These must reference specific items from the milestone description.

Return ONLY raw JSON, no markdown, no backticks:
{{"verdict": "DELIVERED"|"PARTIALLY_DELIVERED"|"NOT_DELIVERED"|"UNVERIFIABLE",
  "confidence": <0-100>,
  "reasoning": "<2-3 sentences citing specific evidence>",
  "delivered_items": ["<item 1>", "<item 2>"],
  "gaps": ["<gap 1>", "<gap 2>"],
  "gap_count": <integer>,
  "sources_readable": <integer>}}"""

                raw = gl.nondet.exec_prompt(prompt, response_format="json")

                try:
                    if isinstance(raw, dict):
                        parsed = raw
                    else:
                        cleaned = str(raw).strip()
                        if cleaned.startswith("```json"):
                            cleaned = cleaned[7:]
                        if cleaned.startswith("```"):
                            cleaned = cleaned[3:]
                        if cleaned.endswith("```"):
                            cleaned = cleaned[:-3]
                        parsed = json.loads(cleaned.strip())

                    verdict = parsed.get("verdict", "UNVERIFIABLE")
                    if verdict not in _VERDICTS:
                        verdict = "UNVERIFIABLE"

                    try:
                        conf = max(0, min(100, int(parsed.get("confidence", 0))))
                    except Exception:
                        conf = 0

                    raw_delivered = parsed.get("delivered_items", [])
                    if not isinstance(raw_delivered, list):
                        raw_delivered = []
                    clean_delivered = []
                    for item in raw_delivered:
                        if item and str(item).strip():
                            clean_delivered.append(str(item))

                    raw_gaps = parsed.get("gaps", [])
                    if not isinstance(raw_gaps, list):
                        raw_gaps = []
                    clean_gaps = []
                    for item in raw_gaps:
                        if item and str(item).strip():
                            clean_gaps.append(str(item))

                    try:
                        gap_count = max(
                            0, int(parsed.get("gap_count", len(clean_gaps)))
                        )
                    except Exception:
                        gap_count = len(clean_gaps)

                    try:
                        claimed_src = int(
                            parsed.get("sources_readable", readable_count)
                        )
                        src_readable = max(
                            0, min(len(evidence_urls_list), claimed_src)
                        )
                    except Exception:
                        src_readable = readable_count

                    # A model cannot claim more readable pages than were fetched.
                    if src_readable > readable_count:
                        src_readable = readable_count

                    # Rule 1: fewer than 2 readable sources forces UNVERIFIABLE.
                    if src_readable < 2:
                        verdict = "UNVERIFIABLE"

                    # Rule 2: PARTIALLY_DELIVERED with no gaps upgrades to DELIVERED.
                    if verdict == "PARTIALLY_DELIVERED" and len(clean_gaps) == 0:
                        verdict = "DELIVERED"

                    # Rule 3: NOT_DELIVERED with more delivered items than gaps
                    # downgrades to PARTIALLY_DELIVERED.
                    if (
                        verdict == "NOT_DELIVERED"
                        and len(clean_delivered) > len(clean_gaps)
                    ):
                        verdict = "PARTIALLY_DELIVERED"

                    if (
                        verdict == "PARTIALLY_DELIVERED"
                        and gap_count < 1
                        and len(clean_gaps) > 0
                    ):
                        gap_count = len(clean_gaps)

                    return {
                        "verdict": verdict,
                        "confidence": conf,
                        "reasoning": str(parsed.get("reasoning", "")),
                        "delivered_items": json.dumps(clean_delivered),
                        "gaps": json.dumps(clean_gaps),
                        "gap_count": gap_count,
                        "sources_readable": src_readable,
                    }
                except Exception as e:
                    return {
                        "verdict": "UNVERIFIABLE",
                        "confidence": 0,
                        "reasoning": "Parse error: " + str(e),
                        "delivered_items": "[]",
                        "gaps": "[]",
                        "gap_count": 0,
                        "sources_readable": readable_count,
                    }
            except Exception as e:
                return {
                    "verdict": "UNVERIFIABLE",
                    "confidence": 0,
                    "reasoning": "Parse error: " + str(e),
                    "delivered_items": "[]",
                    "gaps": "[]",
                    "gap_count": 0,
                    "sources_readable": readable_count,
                }

        def validator_fn(leader_res) -> bool:
            if not isinstance(leader_res, gl.vm.Return):
                return False
            lp = leader_res.calldata
            if not isinstance(lp, dict):
                return False

            leader_verdict = lp.get("verdict")
            leader_conf = lp.get("confidence")
            leader_gaps = lp.get("gap_count", 0)

            if leader_verdict not in _VERDICTS:
                return False
            try:
                lc = int(leader_conf)
                if not (0 <= lc <= 100):
                    return False
            except Exception:
                return False

            try:
                my_result = leader_fn()
            except Exception:
                return False
            if not isinstance(my_result, dict):
                return False

            # Delivery status is the decision. It must match exactly.
            if my_result.get("verdict") != leader_verdict:
                return False

            # PARTIALLY_DELIVERED requires a concrete gap on both sides.
            if leader_verdict == "PARTIALLY_DELIVERED":
                try:
                    my_gaps = int(my_result.get("gap_count", 0))
                    l_gaps = int(leader_gaps)
                    if my_gaps == 0 or l_gaps == 0:
                        return False
                except Exception:
                    return False

            try:
                mc = int(my_result.get("confidence", 0))
                if not (0 <= mc <= 100):
                    return False
            except Exception:
                return False

            def _band(c):
                if c < 35:
                    return 1
                elif c < 80:
                    return 2
                else:
                    return 3

            return _band(mc) == _band(lc)

        ruling = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
        result_data = ruling.calldata if hasattr(ruling, "calldata") else ruling
        if not isinstance(result_data, dict):
            result_data = {
                "verdict": "UNVERIFIABLE",
                "confidence": 0,
                "reasoning": "Invalid nondet result",
                "delivered_items": "[]",
                "gaps": "[]",
                "gap_count": 0,
                "sources_readable": 0,
            }

        result_verdict = result_data.get("verdict", "UNVERIFIABLE")
        if result_verdict not in _VERDICTS:
            result_verdict = "UNVERIFIABLE"

        try:
            conf = max(0, min(100, int(result_data.get("confidence", 0))))
        except Exception:
            conf = 0

        try:
            gap_count = max(0, int(result_data.get("gap_count", 0)))
        except Exception:
            gap_count = 0

        try:
            src_readable = max(0, int(result_data.get("sources_readable", 0)))
        except Exception:
            src_readable = 0

        delivered_raw = result_data.get("delivered_items", "[]")
        if isinstance(delivered_raw, list):
            delivered_raw = json.dumps(delivered_raw)
        elif not isinstance(delivered_raw, str):
            delivered_raw = "[]"

        gaps_raw = result_data.get("gaps", "[]")
        if isinstance(gaps_raw, list):
            gaps_raw = json.dumps(gaps_raw)
        elif not isinstance(gaps_raw, str):
            gaps_raw = "[]"

        report.verdict = result_verdict
        report.confidence = u256(conf)
        report.reasoning = str(result_data.get("reasoning", ""))
        report.delivered_items = delivered_raw
        report.gaps = gaps_raw
        report.gap_count = u256(gap_count)
        report.sources_readable = u256(src_readable)
        if result_verdict == "UNVERIFIABLE" or result_verdict == "":
            report.status = "UNVERIFIABLE"
        else:
            report.status = "VERIFIED"
        self.reports[report_id] = report

    @gl.public.write
    def invalidate_report(self, report_id: str) -> None:
        if report_id not in self.reports:
            raise gl.vm.UserError("Report not found")

        sender = _to_address(gl.message.sender_address)
        if sender != self.owner:
            raise gl.vm.UserError("Only owner")

        report = self.reports[report_id]
        if report.status != "PENDING":
            raise gl.vm.UserError("only PENDING")

        report.status = "UNVERIFIABLE"
        report.reasoning = "Invalidated by admin"
        self.reports[report_id] = report

    @gl.public.view
    def get_report(self, report_id: str) -> str:
        if report_id not in self.reports:
            raise gl.vm.UserError("Report not found")
        return json.dumps(self._report_dict(report_id, self.reports[report_id]))

    @gl.public.view
    def get_verdict(self, report_id: str) -> str:
        if report_id not in self.reports:
            raise gl.vm.UserError("Report not found")

        report = self.reports[report_id]
        if report.status == "PENDING":
            raise gl.vm.UserError("Not yet verified")

        res = {
            "report_id": report_id,
            "project_name": report.project_name,
            "milestone_description": report.milestone_description,
            "claimed_completion_date": report.claimed_completion_date,
            "verdict": report.verdict,
            "confidence": _as_int(report.confidence),
            "reasoning": report.reasoning,
            "delivered_items": report.delivered_items,
            "gaps": report.gaps,
            "gap_count": _as_int(report.gap_count),
            "sources_readable": _as_int(report.sources_readable),
        }
        return json.dumps(res)

    @gl.public.view
    def list_reports(self, verdict_filter: str) -> str:
        if verdict_filter not in _FILTERS:
            raise gl.vm.UserError("Invalid verdict filter")

        results = []
        limit = int(self.next_id)
        for i in range(1, limit):
            report_id = str(i)
            if report_id in self.reports:
                report = self.reports[report_id]
                if (
                    verdict_filter == ""
                    or report.status == verdict_filter
                    or report.verdict == verdict_filter
                ):
                    results.append({
                        "report_id": report_id,
                        "project_name": report.project_name,
                        "milestone_description": report.milestone_description,
                        "claimed_completion_date": report.claimed_completion_date,
                        "status": report.status,
                        "verdict": report.verdict,
                        "gap_count": _as_int(report.gap_count),
                    })
        return json.dumps(results)

    @gl.public.view
    def get_count(self) -> int:
        return int(self.next_id) - 1
