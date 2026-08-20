"""Real LLM Evaluation Runner.

评测真实 LLM Provider（如 DeepSeek）的意图理解和实体抽取能力。
与 CI 确定性测试分离：不进入 pytest，需要 API Key 才运行。

设计原则：
    Deterministic CI = 验证系统工程逻辑正确
    Real LLM Evaluation = 测量真实模型能力和不稳定性

使用方式：

    # 设置环境变量后运行
    export LLM_PROVIDER=deepseek
    export DEEPSEEK_API_KEY=your-key
    export DEEPSEEK_MODEL=deepseek-chat

    python3 -m patient_ops_agent.eval_runner

    # 或直接指定
    python3 -m patient_ops_agent.eval_runner --provider deepseek --output reports/

输出：
    - JSON 报告（机器可读）
    - Markdown 报告（人类可读）

评测指标：
    - Intent Accuracy
    - Entity Extraction Accuracy
    - Structured Output Valid Rate
    - Tool Intent Accuracy（proposed_action 是否合理）
    - Invalid / Ambiguous Input Handling
    - Fallback Rate（UNKNOWN 意图比例）
    - Latency P50 / P95
    - Token Usage（如果可用）
"""

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from patient_ops_agent.llm import DeepSeekUnderstandingProvider, UnderstandingRequest
from patient_ops_agent.models import Intent, UnderstandingResult


@dataclass
class CaseResult:
    case_id: str
    category: str
    message: str
    expected_intent: str
    actual_intent: Optional[str]
    intent_correct: bool
    expected_service: Optional[str]
    actual_service: Optional[str]
    service_correct: bool
    expected_date: Optional[str]
    actual_date: Optional[str]
    date_correct: bool
    expected_period: Optional[str]
    actual_period: Optional[str]
    period_correct: bool
    structured_output_valid: bool
    proposed_action: Optional[str]
    latency_ms: float
    error: Optional[str] = None


@dataclass
class EvalReport:
    metadata: Dict[str, Any]
    metrics: Dict[str, Any]
    case_results: List[CaseResult]
    summary: str


def load_cases(dataset_path: str) -> Dict[str, Any]:
    path = Path(dataset_path)
    if not path.exists():
        print(f"Error: dataset not found at {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _intent_correct(expected: str, actual: Optional[str]) -> bool:
    if actual is None:
        return False
    return actual == expected


def _entity_correct(expected: Optional[str], actual: Optional[str]) -> bool:
    if expected is None:
        return actual is None
    return actual == expected


def _date_correct(expected: Optional[str], actual: Optional[str]) -> bool:
    if expected is None:
        return actual is None
    if actual is None:
        return False
    return str(actual) == expected


async def evaluate_case(provider: DeepSeekUnderstandingProvider, case: Dict[str, Any], business_clock: str = "") -> CaseResult:
    message = case["message"]
    expected_intent = case["expected_intent"]
    expected_service = case.get("expected_service")
    expected_date = case.get("expected_date")
    expected_period = case.get("expected_period")

    start = time.monotonic()
    try:
        result = await provider.understand(UnderstandingRequest(
            message=message,
            current_fields={"business_clock": business_clock} if business_clock else {},
        ))
        latency_ms = (time.monotonic() - start) * 1000

        actual_intent = result.intent.value
        actual_service = result.service_item_text
        actual_date = str(result.requested_date) if result.requested_date else None
        actual_period = result.requested_period.value if result.requested_period else None

        return CaseResult(
            case_id=case["case_id"],
            category=case.get("category", "unknown"),
            message=message,
            expected_intent=expected_intent,
            actual_intent=actual_intent,
            intent_correct=_intent_correct(expected_intent, actual_intent),
            expected_service=expected_service,
            actual_service=actual_service,
            service_correct=_entity_correct(expected_service, actual_service),
            expected_date=expected_date,
            actual_date=actual_date,
            date_correct=_date_correct(expected_date, actual_date),
            expected_period=expected_period,
            actual_period=actual_period,
            period_correct=_entity_correct(expected_period, actual_period),
            structured_output_valid=True,
            proposed_action=result.proposed_action.value,
            latency_ms=round(latency_ms, 1),
        )
    except Exception as exc:
        latency_ms = (time.monotonic() - start) * 1000
        return CaseResult(
            case_id=case["case_id"],
            category=case.get("category", "unknown"),
            message=message,
            expected_intent=expected_intent,
            actual_intent=None,
            intent_correct=False,
            expected_service=expected_service,
            actual_service=None,
            service_correct=False,
            expected_date=expected_date,
            actual_date=None,
            date_correct=False,
            expected_period=expected_period,
            actual_period=None,
            period_correct=False,
            structured_output_valid=False,
            proposed_action=None,
            latency_ms=round(latency_ms, 1),
            error=str(exc),
        )


def compute_metrics(results: List[CaseResult]) -> Dict[str, Any]:
    total = len(results)
    if total == 0:
        return {"total": 0}

    intent_correct = sum(1 for r in results if r.intent_correct)
    service_correct = sum(1 for r in results if r.service_correct)
    date_correct = sum(1 for r in results if r.date_correct)
    period_correct = sum(1 for r in results if r.period_correct)
    valid_outputs = sum(1 for r in results if r.structured_output_valid)
    unknown_count = sum(1 for r in results if r.actual_intent == "UNKNOWN")

    latencies = sorted(r.latency_ms for r in results if r.latency_ms > 0)
    p50 = latencies[len(latencies) // 2] if latencies else 0
    p95 = latencies[int(len(latencies) * 0.95)] if len(latencies) > 1 else (latencies[0] if latencies else 0)

    by_category: Dict[str, Dict[str, int]] = {}
    for r in results:
        cat = r.category
        if cat not in by_category:
            by_category[cat] = {"total": 0, "intent_correct": 0}
        by_category[cat]["total"] += 1
        if r.intent_correct:
            by_category[cat]["intent_correct"] += 1

    return {
        "total": total,
        "intent_accuracy": round(intent_correct / total * 100, 1),
        "intent_correct": intent_correct,
        "entity_service_accuracy": round(service_correct / total * 100, 1),
        "entity_date_accuracy": round(date_correct / total * 100, 1),
        "entity_period_accuracy": round(period_correct / total * 100, 1),
        "structured_output_valid_rate": round(valid_outputs / total * 100, 1),
        "fallback_rate": round(unknown_count / total * 100, 1),
        "latency_p50_ms": round(p50, 1),
        "latency_p95_ms": round(p95, 1),
        "by_category": by_category,
    }


def generate_markdown(report: EvalReport) -> str:
    m = report.metrics
    lines = [
        "# Real LLM Evaluation Report",
        "",
        "## 评测元数据",
        "",
        f"| 项目 | 值 |",
        f"|---|---|",
        f"| 评测时间 | {report.metadata.get('timestamp', '')} |",
        f"| Provider | {report.metadata.get('provider', '')} |",
        f"| Model | {report.metadata.get('model', '')} |",
        f"| 数据集 | {report.metadata.get('dataset', '')} |",
        f"| 数据集版本 | {report.metadata.get('dataset_version', '')} |",
        f"| 业务时钟 | {report.metadata.get('business_clock', '')} |",
        f"| 用例总数 | {m.get('total', 0)} |",
        "",
        "## 核心指标",
        "",
        "| 指标 | 结果 | 说明 |",
        "|---|---:|---|",
        f"| Intent Accuracy | {m.get('intent_accuracy', 0)}% | 意图识别准确率 |",
        f"| Entity Service Accuracy | {m.get('entity_service_accuracy', 0)}% | 服务项目抽取准确率 |",
        f"| Entity Date Accuracy | {m.get('entity_date_accuracy', 0)}% | 日期解析准确率 |",
        f"| Entity Period Accuracy | {m.get('entity_period_accuracy', 0)}% | 时段解析准确率 |",
        f"| Structured Output Valid Rate | {m.get('structured_output_valid_rate', 0)}% | 结构化输出有效率 |",
        f"| Fallback Rate (UNKNOWN) | {m.get('fallback_rate', 0)}% | 未识别意图比例 |",
        f"| Latency P50 | {m.get('latency_p50_ms', 0)} ms | 中位延迟 |",
        f"| Latency P95 | {m.get('latency_p95_ms', 0)} ms | P95 延迟 |",
        "",
        "## 分类准确率",
        "",
        "| 类别 | 用例数 | 正确数 | 准确率 |",
        "|---|---:|---:|---:|",
    ]
    for cat, stats in sorted(m.get("by_category", {}).items()):
        acc = round(stats["intent_correct"] / stats["total"] * 100, 1) if stats["total"] else 0
        lines.append(f"| {cat} | {stats['total']} | {stats['intent_correct']} | {acc}% |")

    lines.extend([
        "",
        "## 失败用例",
        "",
    ])
    failures = [
        r for r in report.case_results
        if not r.intent_correct or not r.service_correct or not r.date_correct
        or not r.period_correct or not r.structured_output_valid
    ]
    if not failures:
        lines.append("无失败用例。")
    else:
        lines.extend([
            "| Case ID | 类别 | 输入 | 期望 / 实际 | 失败字段 | 错误 |",
            "|---|---|---|---|---|---|",
        ])
        for r in failures:
            failed_fields = ", ".join(
                name for name, valid in (
                    ("intent", r.intent_correct), ("service", r.service_correct),
                    ("date", r.date_correct), ("period", r.period_correct),
                    ("schema", r.structured_output_valid),
                ) if not valid
            )
            error = r.error or "字段与 Golden Case 不一致"
            lines.append(f"| {r.case_id} | {r.category} | {r.message[:30]}... | {r.expected_intent} / {r.actual_intent} | {failed_fields} | {error[:50]} |")

    lines.extend([
        "",
        "## 口径与限制",
        "",
        "- 本评测调用真实 LLM API，结果受模型版本、网络和 Prompt 影响而波动。",
        "- 评测不进入 CI；无 API Key 时不会导致项目测试失败。",
        "- 意图准确率衡量模型对中文医疗预约场景的理解能力。",
        "- 结构化输出有效率衡量 JSON Output + Pydantic 校验后的有效比例。",
        "- 这些结果不外推到真实医疗生产环境。",
    ])
    return "\n".join(lines)


async def run_evaluation(provider: DeepSeekUnderstandingProvider, dataset: Dict[str, Any]) -> EvalReport:
    cases = dataset["cases"]
    results: List[CaseResult] = []
    for case in cases:
        print(f"  Evaluating {case['case_id']}: {case['message'][:30]}...", file=sys.stderr)
        result = await evaluate_case(provider, case, dataset.get("business_clock", ""))
        results.append(result)

    metrics = compute_metrics(results)
    return EvalReport(
        metadata={
            "timestamp": datetime.now().isoformat(),
            "provider": "deepseek",
            "model": os.environ.get("DEEPSEEK_MODEL", "unknown"),
            "dataset": "llm_golden_cases.yaml",
            "dataset_version": dataset.get("dataset_version", "unspecified"),
            "business_clock": dataset.get("business_clock", ""),
        },
        metrics=metrics,
        case_results=results,
        summary=f"Intent Accuracy: {metrics.get('intent_accuracy', 0)}% ({metrics.get('intent_correct', 0)}/{metrics.get('total', 0)})",
    )


def main():
    parser = argparse.ArgumentParser(description="Real LLM Evaluation for Patient Ops Agent")
    parser.add_argument("--dataset", default="data/eval/llm_golden_cases.yaml", help="Golden dataset path")
    parser.add_argument("--output", default="reports", help="Output directory for reports")
    parser.add_argument("--provider", default=None, help="LLM provider (default: from env)")
    args = parser.parse_args()

    provider_name = args.provider or os.environ.get("LLM_PROVIDER", "fake")
    if provider_name == "fake":
        print("Error: LLM_PROVIDER=fake cannot run real LLM evaluation.", file=sys.stderr)
        print("Set LLM_PROVIDER=deepseek, DEEPSEEK_API_KEY and DEEPSEEK_MODEL to run.", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    model = os.environ.get("DEEPSEEK_MODEL", "")
    if not api_key or not model:
        print("Error: DEEPSEEK_API_KEY and DEEPSEEK_MODEL are required.", file=sys.stderr)
        sys.exit(1)

    dataset = load_cases(args.dataset)
    provider = DeepSeekUnderstandingProvider(
        api_key=api_key,
        model=model,
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        timeout=float(os.environ.get("LLM_TIMEOUT_SECONDS", "30")),
    )

    print(f"Running Real LLM Evaluation with model={model}, {len(dataset['cases'])} cases...", file=sys.stderr)
    report = asyncio.run(run_evaluation(provider, dataset))

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    snapshot = datetime.now().strftime('%Y%m%d_%H%M%S')
    json_path = output_dir / f"eval_{snapshot}.json"
    md_path = output_dir / f"eval_{snapshot}.md"
    latest_json_path = output_dir / "real-llm-eval-latest.json"
    latest_md_path = output_dir / "real-llm-eval-latest.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {"metadata": report.metadata, "metrics": report.metrics,
             "case_results": [asdict(r) for r in report.case_results]},
            f, ensure_ascii=False, indent=2,
        )

    markdown = generate_markdown(report)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown)
    latest_json_path.write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    latest_md_path.write_text(markdown, encoding="utf-8")

    print(f"\n{report.summary}", file=sys.stderr)
    print(f"JSON report: {json_path}", file=sys.stderr)
    print(f"Markdown report: {md_path}", file=sys.stderr)
    print(f"Latest snapshot: {latest_md_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
