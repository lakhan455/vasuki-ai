from pathlib import Path


def test_v52_pro_removed_from_active_product():
    repo = Path(__file__).resolve().parents[2]
    chat = (repo / "frontend/components/ChatApp.tsx").read_text(encoding="utf-8")
    plans = (repo / "frontend/lib/plans.ts").read_text(encoding="utf-8")
    main_v6 = (repo / "backend/app/main_v6.py").read_text(encoding="utf-8")

    assert "Vasuki Pro" not in chat
    assert "buyVasukiPro" not in plans
    assert "Razorpay" not in plans
    assert "/api/billing/create-order" not in main_v6
    assert "/api/billing/verify" not in main_v6
    assert "/api/billing/webhook" not in main_v6
    assert 'type AiEngine = "vasuki" | "puter"' not in chat
    assert "streamPuterChat(" not in chat
    assert "generatePuterImage4K(" not in chat
