"use client";

import styles from "./ApprovalDialogV77.module.css";

export type ApprovalPromptV77 = {
  title: string;
  risk: "low" | "medium" | "high" | "critical" | string;
  summary: string;
  details: string[];
  expiresInSeconds?: number;
};

export default function ApprovalDialogV77({
  request,
  onDecision,
}: {
  request: ApprovalPromptV77 | null;
  onDecision: (approved: boolean) => void;
}) {
  if (!request) return null;

  const riskKey = String(request.risk || "medium").toLowerCase();
  const riskClass =
    riskKey === "low"
      ? styles.risk_low
      : riskKey === "high"
        ? styles.risk_high
        : riskKey === "critical"
          ? styles.risk_critical
          : styles.risk_medium;

  return (
    <div className={styles.backdrop} role="presentation">
      <section
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="v77-approval-title"
      >
        <div className={styles.header}>
          <div>
            <span className={styles.kicker}>V77 Security Approval</span>
            <h2 id="v77-approval-title">{request.title}</h2>
          </div>
          <span className={`${styles.risk} ${riskClass}`}>
            {String(request.risk || "medium").toUpperCase()} RISK
          </span>
        </div>

        <p className={styles.summary}>{request.summary}</p>

        <div className={styles.details}>
          {request.details.filter(Boolean).map((detail, index) => (
            <div key={`${index}-${detail.slice(0, 24)}`}>{detail}</div>
          ))}
        </div>

        <div className={styles.policy}>
          <strong>One-time approval</strong>
          <span>
            This approval is locked to this exact action and scope. It expires
            automatically and cannot be reused.
          </span>
          {riskKey === "critical" ? (
            <small>Critical credential/payment actions are blocked by policy.</small>
          ) : typeof request.expiresInSeconds === "number" ? (
            <small>Request expires in about {request.expiresInSeconds}s.</small>
          ) : null}
        </div>

        <div className={styles.actions}>
          <button
            type="button"
            className={styles.deny}
            onClick={() => onDecision(false)}
          >
            Deny
          </button>
          <button
            type="button"
            className={styles.approve}
            onClick={() => onDecision(true)}
            disabled={riskKey === "critical"}
          >
            Approve once
          </button>
        </div>
      </section>
    </div>
  );
}
