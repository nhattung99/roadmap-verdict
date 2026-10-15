import json
import pytest


def _payload(
    verdict,
    confidence,
    reasoning,
    delivered_items,
    gaps,
    gap_count,
    sources_readable,
):
    return json.dumps({
        "verdict": verdict,
        "confidence": confidence,
        "reasoning": reasoning,
        "delivered_items": delivered_items,
        "gaps": gaps,
        "gap_count": gap_count,
        "sources_readable": sources_readable,
    })


def _page(text):
    return {"status": 200, "body": text}


def _raise(_url=None):
    raise RuntimeError("source unreachable")


def _submit(contract, direct_vm, caller, project, description, when, urls):
    with direct_vm.prank(caller):
        return contract.submit_milestone(project, description, when, urls)


# 1. Happy path — DELIVERED verdict
def test_delivered_verdict(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/roadmap_verdict.py")

    with direct_vm.prank(direct_alice):
        report_id = contract.submit_milestone(
            "SpaceDAO Protocol",
            "Launch mainnet with staking, bridging, and governance module",
            "Q1 2026",
            [
                "https://github.com/spacedao/releases/v1.0.0",
                "https://spacedao.io/blog/mainnet-launch",
                "https://app.spacedao.io",
            ],
        )
    assert report_id == "1"
    assert contract.get_count() == 1

    direct_vm.mock_web(
        r".*github.*releases.*",
        _page(
            "SpaceDAO v1.0.0 released March 15 2026. "
            "Features: staking module, cross-chain bridge, governance voting."
        ),
    )
    direct_vm.mock_web(
        r".*blog/mainnet.*",
        _page(
            "SpaceDAO mainnet is live! Staking, bridging and governance "
            "are all available as of March 15th 2026."
        ),
    )
    direct_vm.mock_web(
        r".*app.spacedao.*",
        _page("SpaceDAO App | Stake | Bridge | Governance | Connected to mainnet"),
    )
    direct_vm.mock_llm(
        r".*milestone verification.*",
        _payload(
            "DELIVERED",
            94,
            "All three features confirmed by GitHub release and "
            "blog post dated March 2026, within Q1 deadline.",
            ["mainnet launch", "staking module", "bridging", "governance module"],
            [],
            0,
            3,
        ),
    )

    contract.verify_milestone(report_id)

    result = json.loads(contract.get_verdict(report_id))
    assert result["verdict"] == "DELIVERED"
    assert result["confidence"] == 94
    assert result["gap_count"] == 0
    assert json.loads(result["gaps"]) == []
    delivered = json.loads(result["delivered_items"])
    assert len(delivered) == 4

    full = json.loads(contract.get_report(report_id))
    assert full["status"] == "VERIFIED"


# 2. PARTIALLY_DELIVERED — some features missing
def test_partially_delivered(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/roadmap_verdict.py")
    report_id = _submit(
        contract,
        direct_vm,
        direct_alice,
        "NovaSwap",
        "Launch mainnet with staking and DEX integration",
        "Q2 2026",
        [
            "https://novaswap.example/releases/v1",
            "https://novaswap.example/blog/launch",
        ],
    )

    direct_vm.mock_web(
        r".*novaswap.example/releases.*",
        _page(
            "NovaSwap v1 mainnet launched June 2026. Staking contracts are live. "
            "DEX integration is listed as upcoming and is not in this release."
        ),
    )
    direct_vm.mock_web(
        r".*novaswap.example/blog.*",
        _page(
            "NovaSwap mainnet and staking are available. The DEX integration "
            "milestone is still in development and has no public deployment."
        ),
    )
    direct_vm.mock_llm(
        r".*milestone verification.*",
        _payload(
            "PARTIALLY_DELIVERED",
            81,
            "Mainnet and staking are confirmed. DEX integration is not evidenced.",
            ["mainnet", "staking"],
            ["DEX integration"],
            1,
            2,
        ),
    )

    contract.verify_milestone(report_id)

    result = json.loads(contract.get_verdict(report_id))
    assert result["verdict"] == "PARTIALLY_DELIVERED"
    assert result["gap_count"] == 1
    assert json.loads(result["gaps"]) == ["DEX integration"]


# 3. NOT_DELIVERED — no evidence found
def test_not_delivered(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/roadmap_verdict.py")
    report_id = _submit(
        contract,
        direct_vm,
        direct_alice,
        "FutureChain",
        "Ship mainnet, mobile app, and DEX integration",
        "Q1 2026",
        [
            "https://futurechain.example/roadmap",
            "https://futurechain.example/blog/plans",
        ],
    )

    direct_vm.mock_web(
        r".*futurechain.example/roadmap.*",
        _page(
            "FutureChain roadmap. Mainnet, mobile app, and DEX integration "
            "are planned for a later quarter. Nothing is live yet."
        ),
    )
    direct_vm.mock_web(
        r".*futurechain.example/blog.*",
        _page(
            "We hope to start building the mobile app and DEX next year. "
            "There is no mainnet and no shipped product in this update."
        ),
    )
    direct_vm.mock_llm(
        r".*milestone verification.*",
        _payload(
            "NOT_DELIVERED",
            88,
            "Both pages describe future plans. No deliverable is live.",
            [],
            ["mainnet", "mobile app", "DEX integration"],
            3,
            2,
        ),
    )

    contract.verify_milestone(report_id)

    result = json.loads(contract.get_verdict(report_id))
    assert result["verdict"] == "NOT_DELIVERED"
    assert result["gap_count"] == 3
    assert json.loads(contract.get_report(report_id))["status"] == "VERIFIED"


# 4. UNVERIFIABLE — fewer than 2 readable sources
def test_unverifiable_insufficient_sources(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/roadmap_verdict.py")
    report_id = _submit(
        contract,
        direct_vm,
        direct_alice,
        "GhostDAO",
        "Launch mainnet with staking",
        "Q1 2026",
        [
            "https://ghostdao.example/release-missing",
            "https://ghostdao.example/blog-missing",
        ],
    )

    direct_vm.mock_web(r".*ghostdao.example/release-missing.*", _raise)
    direct_vm.mock_web(r".*ghostdao.example/blog-missing.*", _raise)
    direct_vm.mock_llm(
        r".*milestone verification.*",
        _payload(
            "DELIVERED",
            70,
            "The model claimed delivery, but no page could be read.",
            ["mainnet"],
            [],
            0,
            2,
        ),
    )

    contract.verify_milestone(report_id)

    full = json.loads(contract.get_report(report_id))
    assert full["status"] == "UNVERIFIABLE"
    assert full["verdict"] == "UNVERIFIABLE"
    result = json.loads(contract.get_verdict(report_id))
    assert result["verdict"] == "UNVERIFIABLE"
    assert result["sources_readable"] == 0


# 5. UNVERIFIABLE — exactly 1 source readable (below threshold)
def test_unverifiable_one_source(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/roadmap_verdict.py")
    report_id = _submit(
        contract,
        direct_vm,
        direct_alice,
        "OneSource",
        "Launch mainnet with staking",
        "Q1 2026",
        [
            "https://onesource.example/release",
            "https://onesource.example/blog-down",
        ],
    )

    direct_vm.mock_web(
        r".*onesource.example/release.*",
        _page(
            "OneSource mainnet release notes. Staking module is described "
            "as shipped on March 1 2026 in this single page."
        ),
    )
    direct_vm.mock_web(r".*onesource.example/blog-down.*", _raise)
    direct_vm.mock_llm(
        r".*milestone verification.*",
        _payload(
            "DELIVERED",
            90,
            "The model says delivered even though only one source loaded.",
            ["mainnet", "staking"],
            [],
            0,
            3,
        ),
    )

    contract.verify_milestone(report_id)

    result = json.loads(contract.get_verdict(report_id))
    assert result["verdict"] == "UNVERIFIABLE"
    assert result["sources_readable"] == 1
    assert json.loads(contract.get_report(report_id))["status"] == "UNVERIFIABLE"


# 6. All sources fail gracefully — no crash
def test_all_sources_fail_no_crash(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/roadmap_verdict.py")
    report_id = _submit(
        contract,
        direct_vm,
        direct_alice,
        "DownNet",
        "Launch mainnet with a bridge",
        "Q3 2026",
        [
            "https://downnet.example/a",
            "https://downnet.example/b",
            "https://downnet.example/c",
        ],
    )

    direct_vm.mock_web(r".*downnet.example/a.*", _raise)
    direct_vm.mock_web(r".*downnet.example/b.*", _raise)
    direct_vm.mock_web(r".*downnet.example/c.*", _raise)
    direct_vm.mock_llm(
        r".*milestone verification.*",
        _payload(
            "DELIVERED",
            55,
            "Model output is ignored because every fetch failed.",
            ["mainnet"],
            [],
            0,
            3,
        ),
    )

    contract.verify_milestone(report_id)

    full = json.loads(contract.get_report(report_id))
    assert full["status"] == "UNVERIFIABLE"
    assert full["verdict"] == "UNVERIFIABLE"
    assert full["sources_readable"] == 0


# 7. PARTIALLY_DELIVERED consistency: no gaps -> upgraded to DELIVERED
def test_partially_delivered_no_gaps_upgraded(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/roadmap_verdict.py")
    report_id = _submit(
        contract,
        direct_vm,
        direct_alice,
        "UpgradeDAO",
        "Launch mainnet with staking",
        "Q1 2026",
        [
            "https://upgradedao.example/release",
            "https://upgradedao.example/blog",
        ],
    )

    direct_vm.mock_web(
        r".*upgradedao.example/release.*",
        _page("UpgradeDAO mainnet and staking module shipped on March 20 2026."),
    )
    direct_vm.mock_web(
        r".*upgradedao.example/blog.*",
        _page("Blog: UpgradeDAO staking and mainnet are both live as of March 2026."),
    )
    direct_vm.mock_llm(
        r".*milestone verification.*",
        _payload(
            "PARTIALLY_DELIVERED",
            76,
            "The model said partial but listed no missing deliverable.",
            ["mainnet", "staking"],
            [],
            0,
            2,
        ),
    )

    contract.verify_milestone(report_id)

    result = json.loads(contract.get_verdict(report_id))
    assert result["verdict"] == "DELIVERED"
    assert json.loads(result["gaps"]) == []


# 8. NOT_DELIVERED consistency: more delivered than gaps -> downgraded
def test_not_delivered_more_delivered_downgraded(
    direct_vm, direct_deploy, direct_alice
):
    contract = direct_deploy("contracts/roadmap_verdict.py")
    report_id = _submit(
        contract,
        direct_vm,
        direct_alice,
        "MixedDAO",
        "Launch mainnet, staking, and a mobile app",
        "Q2 2026",
        [
            "https://mixeddao.example/release",
            "https://mixeddao.example/app",
        ],
    )

    direct_vm.mock_web(
        r".*mixeddao.example/release.*",
        _page(
            "MixedDAO mainnet and staking are live. The mobile app has no build."
        ),
    )
    direct_vm.mock_web(
        r".*mixeddao.example/app.*",
        _page("MixedDAO product page shows staking and mainnet, not a mobile app."),
    )
    direct_vm.mock_llm(
        r".*milestone verification.*",
        _payload(
            "NOT_DELIVERED",
            64,
            "The model said not delivered, but two of three items are confirmed.",
            ["mainnet", "staking"],
            ["mobile app"],
            1,
            2,
        ),
    )

    contract.verify_milestone(report_id)

    result = json.loads(contract.get_verdict(report_id))
    assert result["verdict"] == "PARTIALLY_DELIVERED"
    assert result["gap_count"] == 1


# 9. Malformed LLM JSON — graceful fallback
def test_malformed_llm_json(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/roadmap_verdict.py")
    report_id = _submit(
        contract,
        direct_vm,
        direct_alice,
        "ParseDAO",
        "Launch mainnet with staking",
        "Q1 2026",
        [
            "https://parsedao.example/release",
            "https://parsedao.example/blog",
        ],
    )

    direct_vm.mock_web(
        r".*parsedao.example/release.*",
        _page("ParseDAO mainnet release notes with staking live since March 2026."),
    )
    direct_vm.mock_web(
        r".*parsedao.example/blog.*",
        _page("ParseDAO blog confirms the mainnet launch and the staking module."),
    )
    direct_vm.mock_llm(r".*milestone verification.*", "not json!!")

    contract.verify_milestone(report_id)

    result = json.loads(contract.get_verdict(report_id))
    assert result["verdict"] == "UNVERIFIABLE"
    full = json.loads(contract.get_report(report_id))
    assert full["status"] == "UNVERIFIABLE"
    assert full["verdict"] == "UNVERIFIABLE"


# 10. LLM returns invalid verdict — normalized to UNVERIFIABLE
def test_invalid_verdict_normalized(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/roadmap_verdict.py")
    report_id = _submit(
        contract,
        direct_vm,
        direct_alice,
        "MaybeDAO",
        "Launch mainnet with staking",
        "Q1 2026",
        [
            "https://maybedao.example/release",
            "https://maybedao.example/blog",
        ],
    )

    direct_vm.mock_web(
        r".*maybedao.example/release.*",
        _page("MaybeDAO published a release note about a possible mainnet launch."),
    )
    direct_vm.mock_web(
        r".*maybedao.example/blog.*",
        _page("MaybeDAO blog discusses staking but does not use a known verdict."),
    )
    direct_vm.mock_llm(
        r".*milestone verification.*",
        _payload(
            "MAYBE_DONE",
            44,
            "The model returned an unknown label.",
            ["mainnet"],
            [],
            0,
            2,
        ),
    )

    contract.verify_milestone(report_id)

    result = json.loads(contract.get_verdict(report_id))
    assert result["verdict"] == "UNVERIFIABLE"
    assert json.loads(contract.get_report(report_id))["status"] == "UNVERIFIABLE"


# 11. delivered_items non-list — handled gracefully
def test_delivered_items_non_list(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/roadmap_verdict.py")
    report_id = _submit(
        contract,
        direct_vm,
        direct_alice,
        "StringDAO",
        "Launch mainnet with staking",
        "Q1 2026",
        [
            "https://stringdao.example/release",
            "https://stringdao.example/blog",
        ],
    )

    direct_vm.mock_web(
        r".*stringdao.example/release.*",
        _page("StringDAO mainnet release. Staking contracts are included in v1."),
    )
    direct_vm.mock_web(
        r".*stringdao.example/blog.*",
        _page("StringDAO announcement: mainnet and staking are available now."),
    )
    direct_vm.mock_llm(
        r".*milestone verification.*",
        json.dumps({
            "verdict": "DELIVERED",
            "confidence": 70,
            "reasoning": "Delivered items arrived as a single string.",
            "delivered_items": "mainnet, staking",
            "gaps": [],
            "gap_count": 0,
            "sources_readable": 2,
        }),
    )

    contract.verify_milestone(report_id)

    result = json.loads(contract.get_verdict(report_id))
    assert result["delivered_items"] == "[]"
    assert result["verdict"] == "DELIVERED"


# 12. Submit with fewer than 2 evidence URLs — UserError
def test_too_few_evidence_urls(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/roadmap_verdict.py")
    with direct_vm.prank(direct_alice):
        with direct_vm.expect_revert("At least 2 evidence URLs required"):
            contract.submit_milestone(
                "Project",
                "Launch mainnet",
                "Q1 2026",
                ["https://github.com/release"],
            )


# 13. Submit with more than 5 evidence URLs — UserError
def test_too_many_evidence_urls(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/roadmap_verdict.py")
    with direct_vm.prank(direct_alice):
        with direct_vm.expect_revert("Maximum 5 evidence URLs"):
            contract.submit_milestone(
                "Project",
                "Launch mainnet",
                "Q1 2026",
                [
                    "https://a.com",
                    "https://b.com",
                    "https://c.com",
                    "https://d.com",
                    "https://e.com",
                    "https://f.com",
                ],
            )


# 14. Submit with invalid URL — UserError
def test_invalid_url_format(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/roadmap_verdict.py")
    with direct_vm.prank(direct_alice):
        with direct_vm.expect_revert("Invalid URL"):
            contract.submit_milestone(
                "Project",
                "Launch mainnet",
                "Q1 2026",
                ["not-a-url", "https://b.com"],
            )


# 15. Submit with duplicate URLs — UserError
def test_duplicate_urls_rejected(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/roadmap_verdict.py")
    with direct_vm.prank(direct_alice):
        with direct_vm.expect_revert("Duplicate"):
            contract.submit_milestone(
                "Project",
                "Launch mainnet",
                "Q1 2026",
                ["https://a.com", "https://a.com"],
            )


# 16. Submit with empty project_name — UserError
def test_empty_project_name(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/roadmap_verdict.py")
    with direct_vm.prank(direct_alice):
        with direct_vm.expect_revert("project_name cannot be empty"):
            contract.submit_milestone(
                "",
                "Launch mainnet",
                "Q1 2026",
                ["https://a.com", "https://b.com"],
            )


# 17. Submit with empty milestone_description — UserError
def test_empty_milestone_description(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/roadmap_verdict.py")
    with direct_vm.prank(direct_alice):
        with direct_vm.expect_revert("milestone_description cannot be empty"):
            contract.submit_milestone(
                "Project",
                "",
                "Q1 2026",
                ["https://a.com", "https://b.com"],
            )


# 18. verify_milestone on already-verified — UserError
def test_verify_already_verified(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/roadmap_verdict.py")
    report_id = _submit(
        contract,
        direct_vm,
        direct_alice,
        "TwiceDAO",
        "Launch mainnet with staking",
        "Q1 2026",
        [
            "https://twicedao.example/release",
            "https://twicedao.example/blog",
        ],
    )

    direct_vm.mock_web(
        r".*twicedao.example/release.*",
        _page("TwiceDAO mainnet and staking module are live as of March 2026."),
    )
    direct_vm.mock_web(
        r".*twicedao.example/blog.*",
        _page("TwiceDAO blog: mainnet launch and staking are both available."),
    )
    direct_vm.mock_llm(
        r".*milestone verification.*",
        _payload(
            "DELIVERED",
            90,
            "Both pages confirm mainnet and staking.",
            ["mainnet", "staking"],
            [],
            0,
            2,
        ),
    )
    contract.verify_milestone(report_id)
    assert json.loads(contract.get_report(report_id))["status"] == "VERIFIED"

    with direct_vm.expect_revert("not PENDING"):
        contract.verify_milestone(report_id)


# 19. get_verdict on PENDING — UserError
def test_get_verdict_pending(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/roadmap_verdict.py")
    with direct_vm.prank(direct_alice):
        report_id = contract.submit_milestone(
            "Project",
            "Launch mainnet",
            "Q1 2026",
            ["https://a.com", "https://b.com"],
        )
    with direct_vm.expect_revert("Not yet verified"):
        contract.get_verdict(report_id)


# 20. list_reports filtering
def test_list_reports_filter(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy("contracts/roadmap_verdict.py")
    delivered_id = _submit(
        contract,
        direct_vm,
        direct_alice,
        "AlphaChain Protocol",
        "Launch mainnet with staking",
        "Q1 2026",
        [
            "https://alphachain.example/release",
            "https://alphachain.example/blog",
        ],
    )
    partial_id = _submit(
        contract,
        direct_vm,
        direct_bob,
        "BetaChain Protocol",
        "Launch mainnet with staking and a DEX",
        "Q2 2026",
        [
            "https://betachain.example/release",
            "https://betachain.example/blog",
        ],
    )
    pending_id = _submit(
        contract,
        direct_vm,
        direct_alice,
        "GammaChain Protocol",
        "Launch a mobile app",
        "Q3 2026",
        [
            "https://gammachain.example/release",
            "https://gammachain.example/blog",
        ],
    )

    direct_vm.mock_web(
        r".*alphachain.example/release.*",
        _page("AlphaChain mainnet and staking module shipped in March 2026."),
    )
    direct_vm.mock_web(
        r".*alphachain.example/blog.*",
        _page("AlphaChain blog confirms mainnet launch and staking are live."),
    )
    direct_vm.mock_llm(
        r".*AlphaChain Protocol.*",
        _payload(
            "DELIVERED",
            93,
            "AlphaChain mainnet and staking are both confirmed.",
            ["mainnet", "staking"],
            [],
            0,
            2,
        ),
    )
    contract.verify_milestone(delivered_id)

    direct_vm.mock_web(
        r".*betachain.example/release.*",
        _page("BetaChain mainnet is live. The DEX integration is not in this build."),
    )
    direct_vm.mock_web(
        r".*betachain.example/blog.*",
        _page("BetaChain shipped mainnet only. DEX integration remains a gap."),
    )
    direct_vm.mock_llm(
        r".*BetaChain Protocol.*",
        _payload(
            "PARTIALLY_DELIVERED",
            72,
            "Mainnet is confirmed and the DEX is missing.",
            ["mainnet"],
            ["DEX"],
            1,
            2,
        ),
    )
    contract.verify_milestone(partial_id)

    delivered = json.loads(contract.list_reports("DELIVERED"))
    partial = json.loads(contract.list_reports("PARTIALLY_DELIVERED"))
    pending = json.loads(contract.list_reports("PENDING"))
    everything = json.loads(contract.list_reports(""))

    assert len(delivered) == 1
    assert delivered[0]["report_id"] == delivered_id
    assert len(partial) == 1
    assert partial[0]["report_id"] == partial_id
    assert len(pending) == 1
    assert pending[0]["report_id"] == pending_id
    assert len(everything) == 3


# 21. invalidate_report — owner only, pending only
def test_invalidate_owner_only(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy("contracts/roadmap_verdict.py")
    report_id = _submit(
        contract,
        direct_vm,
        direct_alice,
        "OwnedDAO",
        "Launch mainnet",
        "Q1 2026",
        [
            "https://owneddao.example/release",
            "https://owneddao.example/blog",
        ],
    )

    with direct_vm.prank(direct_bob):
        with direct_vm.expect_revert("Only owner"):
            contract.invalidate_report(report_id)

    contract.invalidate_report(report_id)
    full = json.loads(contract.get_report(report_id))
    assert full["status"] == "UNVERIFIABLE"
    assert full["reasoning"] == "Invalidated by admin"


# 22. invalidate already-verified — UserError
def test_invalidate_non_pending(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/roadmap_verdict.py")
    report_id = _submit(
        contract,
        direct_vm,
        direct_alice,
        "LockedDAO",
        "Launch mainnet with staking",
        "Q1 2026",
        [
            "https://lockeddao.example/release",
            "https://lockeddao.example/blog",
        ],
    )

    direct_vm.mock_web(
        r".*lockeddao.example/release.*",
        _page("LockedDAO mainnet and staking are live according to the release."),
    )
    direct_vm.mock_web(
        r".*lockeddao.example/blog.*",
        _page("LockedDAO blog post confirms the mainnet launch and staking module."),
    )
    direct_vm.mock_llm(
        r".*milestone verification.*",
        _payload(
            "DELIVERED",
            86,
            "Release and blog both confirm the milestone.",
            ["mainnet", "staking"],
            [],
            0,
            2,
        ),
    )
    contract.verify_milestone(report_id)

    with direct_vm.expect_revert("only PENDING"):
        contract.invalidate_report(report_id)


# 23. Multiple gaps stored and retrievable
def test_multiple_gaps_stored(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/roadmap_verdict.py")
    report_id = _submit(
        contract,
        direct_vm,
        direct_alice,
        "GapDAO",
        "Launch mainnet, mobile app, DEX integration, and a bridge",
        "Q4 2026",
        [
            "https://gapdao.example/release",
            "https://gapdao.example/blog",
        ],
    )

    direct_vm.mock_web(
        r".*gapdao.example/release.*",
        _page(
            "GapDAO mainnet is live. Mobile app, DEX integration, and the bridge "
            "are absent from this release and have no deployment addresses."
        ),
    )
    direct_vm.mock_web(
        r".*gapdao.example/blog.*",
        _page(
            "GapDAO announced mainnet only. The mobile app, DEX, and bridge "
            "are still on the roadmap and not shipped."
        ),
    )
    gaps = ["mobile app", "DEX integration", "bridge"]
    direct_vm.mock_llm(
        r".*milestone verification.*",
        _payload(
            "PARTIALLY_DELIVERED",
            84,
            "Only mainnet is confirmed. Three promised pieces are missing.",
            ["mainnet"],
            gaps,
            3,
            2,
        ),
    )

    contract.verify_milestone(report_id)

    result = json.loads(contract.get_verdict(report_id))
    parsed = json.loads(result["gaps"])
    assert result["verdict"] == "PARTIALLY_DELIVERED"
    assert len(parsed) == 3
    for entry in parsed:
        assert isinstance(entry, str)
        assert len(entry.strip()) > 0


# 24. Exactly 2 sources readable — passes threshold
def test_exactly_two_sources_readable(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/roadmap_verdict.py")
    report_id = _submit(
        contract,
        direct_vm,
        direct_alice,
        "TwoSource",
        "Launch mainnet with staking",
        "Q1 2026",
        [
            "https://twosource.example/release",
            "https://twosource.example/blog",
            "https://twosource.example/down",
        ],
    )

    direct_vm.mock_web(
        r".*twosource.example/release.*",
        _page("TwoSource v1 mainnet release includes the staking module, March 2026."),
    )
    direct_vm.mock_web(
        r".*twosource.example/blog.*",
        _page("TwoSource blog: mainnet and staking went live on March 18 2026."),
    )
    direct_vm.mock_web(r".*twosource.example/down.*", _raise)
    direct_vm.mock_llm(
        r".*milestone verification.*",
        _payload(
            "DELIVERED",
            91,
            "Two readable pages confirm mainnet and staking inside Q1 2026.",
            ["mainnet", "staking"],
            [],
            0,
            2,
        ),
    )

    contract.verify_milestone(report_id)

    result = json.loads(contract.get_verdict(report_id))
    assert result["verdict"] == "DELIVERED"
    assert result["sources_readable"] == 2
    assert json.loads(contract.get_report(report_id))["status"] == "VERIFIED"
