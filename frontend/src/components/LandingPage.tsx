"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowDownRight, ArrowRight, Check, ChevronDown, FileText, ScanLine, ShieldCheck } from "lucide-react";

type FlowStage = "request" | "review" | "draft";

const flowCopy: Record<FlowStage, { label: string; title: string; body: string }> = {
  request: {
    label: "01 / Intake",
    title: "Start with the request you received.",
    body: "Paste email text or add a PDF, spreadsheet, or CSV. Keep the original close as line items are proposed.",
  },
  review: {
    label: "02 / Review",
    title: "Check each line against your catalog.",
    body: "Manufacturer and part number guide exact matching. Missing or unclear fields stay visible for a person to resolve.",
  },
  draft: {
    label: "03 / Prepare",
    title: "Build a worksheet when the lines are ready.",
    body: "Review the rows, inspect their source, and export a quotation-preparation draft for your existing process.",
  },
};

const stageOrder: FlowStage[] = ["request", "review", "draft"];

function BrandMark() {
  return (
    <span className="landing-mark" aria-hidden="true">
      <svg viewBox="0 0 40 40" fill="none">
        <path d="M10 6h13l8 8v20H10V6Z" stroke="currentColor" strokeWidth="1.7" />
        <path d="M23 6v9h8M15 21h11M15 26h7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <path d="m24 29 3 3 6-7" stroke="var(--landing-orange)" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );
}

function Reveal({ children, className = "", variant = "rise" }: { children: ReactNode; className?: string; variant?: "rise" | "shutter" | "soft" }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node || !("IntersectionObserver" in window)) {
      node?.classList.add("is-visible");
      return;
    }
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        node.classList.add("is-visible");
        observer.unobserve(node);
      }
    }, { threshold: 0.14, rootMargin: "0px 0px -6% 0px" });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return <div ref={ref} className={`landing-reveal landing-reveal--${variant} ${className}`}>{children}</div>;
}

function ProductFragment({ stage }: { stage: FlowStage }) {
  return (
    <div className="product-fragment" data-ui aria-live="polite" aria-label={`Illustrative product view: ${flowCopy[stage].label}`}>
      <div className="fragment-head">
        <div className="fragment-file-icon"><FileText size={16} aria-hidden="true" /></div>
        <div className="fragment-source">
          <span className="fragment-kicker">ILLUSTRATIVE RFQ</span>
          <strong>{stage === "request" ? "pasted_inquiry.txt" : stage === "review" ? "Controls cabinet parts" : "Draft worksheet"}</strong>
        </div>
        <span className={`fragment-state fragment-state--${stage}`}><i />{stage === "request" ? "Parsed" : stage === "review" ? "Needs review" : "Draft only"}</span>
      </div>

      {stage === "request" && (
        <div className="fragment-paper">
          <span className="fragment-paper-rule fragment-paper-rule--wide" />
          <span className="fragment-paper-rule" />
          <span className="fragment-paper-line"><b>1</b><span>Contactor, 24 VDC coil</span><code>10 pcs</code></span>
          <span className="fragment-paper-line"><b>2</b><span>Digital I/O module</span><code>4 units</code></span>
          <span className="fragment-paper-rule fragment-paper-rule--short" />
          <span className="fragment-provenance"><ScanLine size={13} aria-hidden="true" /> Source preserved · pasted text</span>
        </div>
      )}

      {stage === "review" && (
        <div className="fragment-table">
          <div className="fragment-table-head"><span>LINE</span><span>MANUFACTURER PART NO.</span><span>REVIEW</span></div>
          <div className="fragment-table-row"><b>01</b><span className="fragment-part"><small>Example Controls</small><code>EC-24V-R2</code></span><span className="fragment-pill fragment-pill--exact"><Check size={11} /> Exact IDs</span></div>
          <div className="fragment-table-row fragment-table-row--selected"><b>02</b><span className="fragment-part"><small>Manufacturer missing</small><code>NS-IO-14</code></span><span className="fragment-pill fragment-pill--review">Review</span></div>
          <div className="fragment-origin"><span className="origin-pin" /> Selected row · source line 2</div>
        </div>
      )}

      {stage === "draft" && (
        <div className="fragment-draft">
          <div className="draft-title"><span>QUOTATION PREPARATION</span><strong>RFQ worksheet</strong></div>
          <div className="draft-columns"><span>Requested item</span><span>Qty</span><span>Catalog SKU</span></div>
          <div className="draft-row"><span>Contactor, 24 VDC coil</span><b>10</b><span>Reviewed</span></div>
          <div className="draft-row"><span>Digital I/O module</span><b>4</b><span>Needs review</span></div>
          <div className="draft-notice"><ShieldCheck size={14} /> Draft for human review. No quote is sent.</div>
        </div>
      )}

      <div className="fragment-foot"><span>{flowCopy[stage].label}</span><span className="fragment-foot-mark">RFQ / A</span></div>
    </div>
  );
}

function FlowStory({ stage, onStageChange }: { stage: FlowStage; onStageChange: (stage: FlowStage) => void }) {
  const itemRefs = useRef<Record<FlowStage, HTMLButtonElement | null>>({ request: null, review: null, draft: null });

  useEffect(() => {
    const buttons = stageOrder.map((key) => itemRefs.current[key]).filter(Boolean) as HTMLButtonElement[];
    if (!buttons.length || !("IntersectionObserver" in window)) return;
    const observer = new IntersectionObserver((entries) => {
      const active = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      const next = active?.target.getAttribute("data-stage") as FlowStage | null;
      if (next) onStageChange(next);
    }, { threshold: [0.35, 0.6], rootMargin: "-18% 0px -18% 0px" });
    buttons.forEach((button) => observer.observe(button));
    return () => observer.disconnect();
  }, [onStageChange]);

  return (
    <div className="flow-layout">
      <div className="flow-steps">
        {stageOrder.map((key) => {
          const step = flowCopy[key];
          return (
            <button
              type="button"
              key={key}
              ref={(node) => { itemRefs.current[key] = node; }}
              data-stage={key}
              aria-pressed={stage === key}
              className={`flow-step ${stage === key ? "is-active" : ""}`}
              onClick={() => onStageChange(key)}
            >
              <span className="flow-step-label">{step.label}</span>
              <span className="flow-step-title">{step.title}</span>
              <span className="flow-step-body">{step.body}</span>
              <span className="flow-step-action" aria-hidden="true">{stage === key ? "Showing example" : "View this stage"}<ArrowRight size={14} /></span>
            </button>
          );
        })}
      </div>
      <div className="flow-stage-wrap">
        <div className="flow-stage-caption"><span>THE WORKFLOW</span><span>Illustrative sample data</span></div>
        <ProductFragment stage={stage} />
        <p className="fragment-caption">Sample values illustrate the interface. Matching depends on the catalog supplied for a workspace.</p>
      </div>
    </div>
  );
}

function Question({ question, children }: { question: string; children: ReactNode }) {
  return (
    <details className="landing-question">
      <summary>{question}<ChevronDown size={18} aria-hidden="true" /></summary>
      <div className="landing-answer">{children}</div>
    </details>
  );
}

export default function LandingPage() {
  const [stage, setStage] = useState<FlowStage>("request");

  useEffect(() => {
    document.documentElement.classList.add("landing-motion-enabled");
    return () => document.documentElement.classList.remove("landing-motion-enabled");
  }, []);

  return (
    <main className="landing-page">
      <header className="landing-nav">
        <Link className="landing-wordmark" href="/" aria-label="RFQ Assistant home">
          <BrandMark />
          <span>RFQ Assistant</span>
        </Link>
        <nav aria-label="Landing page navigation">
          <a href="#workflow">Workflow</a>
          <a href="#matching">Matching</a>
          <a href="#review">Review</a>
        </nav>
        <Link className="landing-nav-cta" href="/workspace">Open workspace <ArrowRight size={15} /></Link>
      </header>

      <section className="landing-hero" aria-labelledby="hero-title">
        <Image className="hero-photo" src="/landing/distributor-workbench.jpg" alt="Illustrative industrial components workbench with a paper parts request" fill priority sizes="100vw" />
        <div className="hero-shade" />
        <div className="hero-content">
          <p className="hero-kicker">Quotation preparation for industrial distributors</p>
          <h1 id="hero-title">See what goes<br />into <em>a quote.</em></h1>
          <p className="hero-copy">Turn incoming parts requests into source-linked line review and a draft worksheet. Your team stays in control.</p>
          <div className="hero-actions">
            <Link className="button-light" href="/workspace">Open workspace <ArrowRight size={16} /></Link>
            <a className="hero-text-link" href="#workflow">See how it works <ArrowDownRight size={16} /></a>
          </div>
        </div>
        <div className="hero-note" aria-label="Illustrative RFQ data sample">
          <div className="hero-note-top"><span>ILLUSTRATIVE REQUEST</span><span className="hero-note-status"><i /> In review</span></div>
          <div className="hero-note-body">
            <div><b>01</b><span>Contactor<br /><small>10 pcs · source line 1</small></span><Check size={15} /></div>
            <div><b>02</b><span>Digital I/O module<br /><small>4 units · source line 2</small></span><span className="hero-review-dot" /></div>
          </div>
          <div className="hero-note-bottom"><span>2 proposed lines</span><span>Human review required</span></div>
        </div>
        <div className="hero-bottomline"><span>01 — A request, made reviewable</span><span>Illustrative imagery and sample data</span></div>
      </section>

      <section className="landing-statement" aria-labelledby="statement-title">
        <Reveal variant="soft" className="statement-copy">
          <p className="section-kicker">A clearer quotation workflow</p>
          <h2 id="statement-title">Requests arrive.<br /><span>Review stays clear.</span></h2>
        </Reveal>
        <Reveal variant="shutter" className="statement-image-wrap">
          <Image src="/landing/request-on-workbench.jpg" alt="Illustrative paper request and component samples on a distributor workbench" fill sizes="(max-width: 800px) 100vw, 44vw" />
          <span className="image-caption">Illustrative scene · the paper trail starts with the request.</span>
        </Reveal>
        <Reveal variant="rise" className="statement-aside">
          <p>RFQs arrive as email text, spreadsheets, PDFs, and CSVs. The assistant turns them into editable line items while keeping the source nearby.</p>
          <a href="#workflow" className="inline-link">Follow one through <ArrowRight size={15} /></a>
        </Reveal>
      </section>

      <section id="workflow" className="landing-workflow" aria-labelledby="workflow-title">
        <div className="workflow-intro">
          <Reveal>
            <p className="section-kicker">From request to worksheet</p>
          <h2 id="workflow-title">It shows<br />its work.</h2>
            <p className="workflow-lead">A short path through the parts of quotation prep that deserve a second look.</p>
          </Reveal>
        </div>
        <FlowStory stage={stage} onStageChange={setStage} />
      </section>

      <section id="matching" className="landing-matching" aria-labelledby="matching-title">
        <div className="matching-copy">
          <Reveal>
            <p className="section-kicker">Catalog matching</p>
            <h2 id="matching-title">Exact means<br /><em>both IDs agree.</em></h2>
            <p>Manufacturer and normalized part number are checked against the catalog supplied for the workspace. A similar description is not proof that two components can replace one another.</p>
            <ul className="matching-points">
              <li><span>Manufacturer</span><span>Must align</span></li>
              <li><span>Part number</span><span>Exact lookup</span></li>
              <li><span>Unclear or missing</span><span>Needs review</span></li>
            </ul>
          </Reveal>
        </div>
        <Reveal variant="shutter" className="matching-photo">
          <Image src="/landing/component-drawers.jpg" alt="Illustrative drawers of industrial electrical components" fill sizes="(max-width: 800px) 100vw, 54vw" />
          <div className="match-overlay" data-ui>
            <div className="match-overlay-head"><span>AUTHORIZED CATALOG</span><span>Sample row</span></div>
            <div className="match-overlay-row"><span>Manufacturer</span><b>Example Controls</b></div>
            <div className="match-overlay-row"><span>Part number</span><code>EX-2048-R2</code></div>
            <div className="match-overlay-foot"><Check size={14} /> Exact identifiers shown for illustration</div>
          </div>
          <span className="image-caption">Illustrative components · sample identifiers in the panel.</span>
        </Reveal>
      </section>

      <section id="review" className="landing-review" aria-labelledby="review-title">
        <Reveal variant="shutter" className="review-photo">
          <Image src="/landing/catalog-review.jpg" alt="Illustrative distributor checking a component against a printed request" fill sizes="(max-width: 800px) 100vw, 48vw" />
          <span className="image-caption">Illustrative distributor scene · the reviewer stays close to the source.</span>
        </Reveal>
        <Reveal className="review-copy">
          <p className="section-kicker">A person makes the call</p>
          <h2 id="review-title">A person<br /><em>makes the call.</em></h2>
          <p>Correct quantities, inspect where a value came from, and resolve each line before preparing a worksheet. Review actions are recorded in the case history.</p>
          <div className="review-rule"><ShieldCheck size={20} /><span>Quotes are not sent automatically. Unverified substitutions are not approved for you.</span></div>
          <Link className="inline-link" href="/workspace">Explore the workspace <ArrowRight size={15} /></Link>
        </Reveal>
      </section>

      <section className="landing-questions" aria-labelledby="questions-title">
        <Reveal className="questions-heading">
          <p className="section-kicker">Before you begin</p>
          <h2 id="questions-title">A few clear answers.</h2>
        </Reveal>
        <div className="question-list">
          <Question question="What kinds of requests can I add?">The prototype accepts pasted RFQ text and supported PDF, XLSX, and CSV files. The original input remains available for review.</Question>
          <Question question="How are catalog matches selected?">The first version checks manufacturer and normalized manufacturer part number against a catalog you provide. Description similarity is not treated as engineering evidence.</Question>
          <Question question="Does it send quotes to customers?">No. It prepares a worksheet and an unsent reply draft. A person must review the lines and take any next action.</Question>
        </div>
      </section>

      <section className="landing-cta" aria-labelledby="cta-title">
        <div className="cta-image"><Image src="/landing/distributor-workbench.jpg" alt="Illustrative component distributor workbench" fill sizes="100vw" /></div>
        <div className="cta-shade" />
        <Reveal className="cta-content">
          <p className="section-kicker">Start with a request</p>
          <h2 id="cta-title">Prepare a<br /><em>better draft.</em></h2>
          <p>Open the local workspace to inspect the workflow with your own sample files.</p>
          <Link className="button-light" href="/workspace">Open workspace <ArrowRight size={16} /></Link>
        </Reveal>
        <span className="cta-image-note">Illustrative generated imagery</span>
      </section>

      <footer className="landing-footer">
        <Link className="landing-wordmark" href="/" aria-label="RFQ Assistant home"><BrandMark /><span>RFQ Assistant</span></Link>
        <p>Quotation preparation for independent industrial distributors.</p>
        <Link className="footer-app-link" href="/workspace">Open workspace <ArrowRight size={15} /></Link>
        <span className="footer-boundary">Human-reviewed. Draft-only.</span>
      </footer>
    </main>
  );
}
