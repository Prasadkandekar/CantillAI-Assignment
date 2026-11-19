import React from "react";
import { Link, Navigate } from "react-router-dom";
import { warmUp } from "../api.js";
import { useAuth } from "../auth/useAuth.js";
import Icon from "../components/Icon.jsx";
import SpikeMark, { PageLoader } from "../components/SpikeMark.jsx";
import Typewriter from "../components/Typewriter.jsx";

const reduced = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

// Fades and slides children in once when scrolled into view.
function Reveal({ delay = 0, className = "", children }) {
  const ref = React.useRef(null);
  const [seen, setSeen] = React.useState(() => reduced() || typeof IntersectionObserver === "undefined");
  React.useEffect(() => {
    if (seen) return undefined;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setSeen(true);
          io.disconnect();
        }
      },
      { threshold: 0.15 }
    );
    if (ref.current) io.observe(ref.current);
    return () => io.disconnect();
  }, [seen]);
  return (
    <div ref={ref} className={`${seen ? "animate-fade-up" : "opacity-0"} ${className}`} style={{ animationDelay: `${delay}ms` }}>
      {children}
    </div>
  );
}

const CHAT_LINES = [
  { text: "you  100 pairs of nitrile gloves for Chakan by Friday", className: "text-on-dark" },
  { text: "corvo  Matched item and plant. Please check the card:", className: "text-on-dark-soft" },
  { text: "  item      nitrile gloves, 100 pairs", className: "text-teal" },
  { text: "  plant     Chakan", className: "text-teal" },
  { text: "  need by   Friday (IST)", className: "text-teal" },
  { text: "you  Confirm", className: "text-on-dark" },
  { text: "corvo  PR created. Active policy applied.", className: "text-on-dark-soft" },
  { text: "  route     CONTRACT_PO, clause and policy version saved", className: "text-primary" },
];

const FEATURES = [
  {
    icon: "chat",
    title: "Raise a request by chat",
    body: "Employees describe what they need in plain words. The assistant asks when an item, quantity or plant is unclear and never guesses.",
  },
  {
    icon: "shield",
    title: "Policy applied for you",
    body: "Each request is routed against the active policy: a rate contract, the preferred supplier, or a request for quotes. The same input always gives the same result.",
  },
  {
    icon: "file",
    title: "Every decision explains itself",
    body: "Buyers see the clause, the policy version, the contract or PO relied on and the facts that made the rule fire, then approve or override.",
  },
];

const STEPS = [
  { icon: "chat", title: "Chat intake", body: "Free text becomes structured fields." },
  { icon: "swap", title: "Decision engine", body: "Match, club, value, contracts, rules." },
  { icon: "inbox", title: "Buyer workspace", body: "Review the reasoning and act." },
  { icon: "upload", title: "Policy and batch", body: "Update policy as data and run CSV batches." },
];

function Wordmark({ dark = false }) {
  return (
    <span className={`inline-flex items-center gap-xs font-serif text-title-lg ${dark ? "text-on-dark" : "text-ink"}`}>
      <SpikeMark size={22} className="text-primary" />
      Corvo
    </span>
  );
}

export default function LandingPage() {
  const { user, status } = useAuth();
  React.useEffect(() => {
    warmUp(); // wake the backend and database while the visitor reads the page
  }, []);
  if (status === "loading") return <PageLoader />;
  if (user) return <Navigate to="/chat" replace />;

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="sticky top-0 z-30 border-b border-hairline-soft bg-canvas">
        <nav className="mx-auto flex h-16 max-w-content items-center justify-between px-lg" aria-label="Main">
          <Wordmark />
          <Link to="/login" className="btn-secondary">
            Sign in
          </Link>
        </nav>
      </header>

      <main>
        {/* Hero: cream */}
        <section className="bg-canvas py-section">
          <div className="mx-auto grid max-w-content items-center gap-xxl px-lg md:grid-cols-2">
            <div>
              <p className="eyebrow mb-md text-primary">Procurement, by policy</p>
              <h1 className="display-xl animate-fade-up">Purchase requests become purchase orders.</h1>
              <p className="mt-lg max-w-xl animate-fade-up text-body-md text-body [animation-delay:80ms]">
                Corvo takes a request by chat, applies the active procurement policy and hands buyers a decision they can read, trust and act on.
              </p>
              <div className="mt-xl flex animate-fade-up flex-wrap gap-sm [animation-delay:160ms]">
                <Link to="/login" className="btn-primary">
                  Get started
                  <Icon name="arrow-right" size={16} />
                </Link>
                <a href="#how-it-works" className="btn-secondary">
                  See how it works
                </a>
              </div>
            </div>
            <div className="animate-fade-up rounded-lg bg-surface-dark p-lg text-on-dark shadow-pop [animation-delay:240ms]">
              <div className="mb-md flex items-center gap-xs" aria-hidden="true">
                <span className="h-3 w-3 rounded-pill bg-error" />
                <span className="h-3 w-3 rounded-pill bg-amber" />
                <span className="h-3 w-3 rounded-pill bg-success" />
                <span className="ml-sm text-caption text-on-dark-soft">chat · PR to PO</span>
              </div>
              <Typewriter lines={CHAT_LINES} className="font-mono text-code" />
            </div>
          </div>
        </section>

        {/* Features: cream */}
        <section id="how-it-works" className="bg-canvas pb-section">
          <div className="mx-auto max-w-content px-lg">
            <Reveal>
              <h2 className="display-md max-w-2xl">Fast for requesters. Clear for buyers.</h2>
            </Reveal>
            <div className="mt-xxl grid gap-lg md:grid-cols-3">
              {FEATURES.map((f, i) => (
                <Reveal key={f.title} delay={i * 100}>
                  <div className="card-feature h-full">
                    <span className="mb-lg flex h-10 w-10 items-center justify-center rounded-md bg-canvas text-primary">
                      <Icon name={f.icon} size={20} />
                    </span>
                    <h3 className="mb-xs text-title-md font-medium">{f.title}</h3>
                    <p className="text-body-sm text-body">{f.body}</p>
                  </div>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        {/* Product mockup: dark */}
        <section className="bg-surface-dark py-section text-on-dark">
          <div className="mx-auto max-w-content px-lg">
            <Reveal>
              <p className="eyebrow mb-md text-primary">From request to order</p>
              <h2 className="display-md max-w-2xl text-on-dark">One engine, four steps, nothing hidden.</h2>
              <p className="mt-md max-w-2xl text-body-md text-on-dark-soft">
                An AI model only translates text into fields. The route, the price and the supplier come from a deterministic engine reading versioned policy data.
              </p>
            </Reveal>
            <div className="mt-xxl grid gap-md sm:grid-cols-2 lg:grid-cols-4">
              {STEPS.map((s, i) => (
                <Reveal key={s.title} delay={i * 100}>
                  <div className="h-full rounded-lg bg-surface-dark-elevated p-lg">
                    <span className="mb-md flex h-9 w-9 items-center justify-center rounded-md bg-surface-dark-soft text-primary">
                      <Icon name={s.icon} size={18} />
                    </span>
                    <p className="mb-xxs text-caption-uppercase uppercase text-on-dark-soft">Step {i + 1}</p>
                    <h3 className="mb-xs text-title-sm font-medium text-on-dark">{s.title}</h3>
                    <p className="text-body-sm text-on-dark-soft">{s.body}</p>
                  </div>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        {/* Callout: coral band on cream */}
        <section className="bg-canvas py-section">
          <div className="mx-auto max-w-content px-lg">
            <Reveal>
              <div className="card-coral flex flex-col items-start justify-between gap-lg md:flex-row md:items-center">
                <div>
                  <h2 className="display-sm text-on-primary">Ready to raise your first request?</h2>
                  <p className="mt-xs text-body-md text-on-primary">Sign in with your work email and pick your role.</p>
                </div>
                <Link to="/login" className="btn-secondary shrink-0">
                  Sign in
                  <Icon name="arrow-right" size={16} />
                </Link>
              </div>
            </Reveal>
          </div>
        </section>
      </main>

      {/* Footer: dark */}
      <footer className="bg-surface-dark py-xxl text-on-dark-soft">
        <div className="mx-auto flex max-w-content flex-col items-start justify-between gap-md px-lg sm:flex-row sm:items-center">
          <Wordmark dark />
          <p className="text-body-sm">PR to PO for Cantill and Corvo procurement.</p>
        </div>
      </footer>
    </div>
  );
}
