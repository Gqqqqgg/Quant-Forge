import { useEffect, useState, type MouseEvent } from "react";
import { ChartNoAxesCombined, FlaskConical, Layers3, Shapes } from "lucide-react";
import { BacktestsPage, FactorsPage, NotFound, StrategiesPage } from "@/components/catalog-pages";

export default function App() {
  const [path, setPath] = useState(() => window.location.pathname);
  useEffect(() => {
    const update = () => setPath(window.location.pathname);
    window.addEventListener("popstate", update);
    if (window.location.pathname === "/") {
      window.history.replaceState(null, "", "/strategies"); update();
    }
    return () => window.removeEventListener("popstate", update);
  }, []);
  const match = /^\/(factors|strategies|backtests)(?:\/([^/]+))?\/?$/.exec(path);
  const section = match?.[1] ?? (path === "/" ? "strategies" : "");
  const id = match?.[2];
  useEffect(() => {
    document.title = `${section === "factors" ? "因子" : section === "backtests" ? "回测" : "策略"} · Quant Forge`;
    window.scrollTo(0, 0);
  }, [path, section]);
  function navigate(event: MouseEvent<HTMLDivElement>) {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = (event.target as HTMLElement).closest("a");
    if (!link || link.target || link.hasAttribute("download") || link.origin !== window.location.origin) return;
    event.preventDefault(); window.history.pushState(null, "", link.href); setPath(link.pathname);
  }
  const links = [
    { href: "/factors", title: "因子", icon: Shapes, key: "factors" },
    { href: "/strategies", title: "策略", icon: Layers3, key: "strategies" },
    { href: "/backtests", title: "回测", icon: FlaskConical, key: "backtests" },
  ];
  return <div className="min-h-screen lg:grid lg:grid-cols-[220px_1fr]" onClick={navigate}>
    <aside className="border-b bg-card px-5 py-5 lg:sticky lg:top-0 lg:h-screen lg:border-r lg:border-b-0 lg:py-8">
      <a href="/strategies" className="flex items-center gap-3 font-semibold tracking-tight"><span className="rounded-lg bg-primary p-2 text-white"><ChartNoAxesCombined size={20} /></span>Quant Forge</a>
      <p className="mt-3 hidden text-xs text-muted-foreground lg:block">量化研究工作台</p>
      <nav aria-label="主导航" className="mt-5 flex gap-2 lg:mt-10 lg:flex-col">{links.map((link) => <a key={link.href} href={link.href} aria-current={section === link.key ? "page" : undefined} className={`flex items-center gap-3 rounded-lg px-4 py-3 text-sm transition-colors ${section === link.key ? "bg-primary/10 font-medium text-primary" : "text-muted-foreground hover:bg-secondary hover:text-foreground"}`}><link.icon size={18} />{link.title}</a>)}</nav>
      <p className="absolute bottom-8 hidden text-xs text-muted-foreground lg:block">因子 → 策略 → 回测</p>
    </aside>
    <main className="mx-auto w-full max-w-7xl px-5 py-8 sm:px-9 lg:py-12">
      {section === "factors" ? <FactorsPage id={id} /> : section === "strategies" ? <StrategiesPage key={id ?? "list"} id={id} /> : section === "backtests" ? <BacktestsPage id={id} /> : <NotFound />}
    </main>
  </div>;
}
