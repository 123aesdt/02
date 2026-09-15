import { Leaf, Network, ShieldCheck, Truck } from "lucide-react";

import { LogisticsRoute } from "./logistics-route";

const capabilities = [
  { icon: Truck, title: "高效配送", detail: "更快更准" },
  { icon: ShieldCheck, title: "安全可靠", detail: "全程可控" },
  { icon: Leaf, title: "绿色低碳", detail: "践行环保" },
  { icon: Network, title: "城乡一体", detail: "连接美好" },
] as const;

export function LoginHero() {
  return <section className="county-login__hero" aria-labelledby="county-login-title">
    <div className="county-login__brand county-login__reveal county-login__reveal--brand">
      <span className="county-login__brand-mark" aria-hidden="true"><i /><i /><i /></span>
      <span><strong>县域物流</strong><small>COUNTY LOGISTICS</small></span>
      <b aria-hidden="true" />
      <em>让县域更高效，让生活更美好</em>
    </div>

    <div className="county-login__message">
      <h1 id="county-login-title" className="county-login__reveal county-login__reveal--title">
        <span>县域物流</span>
        <strong>智慧配送平台</strong>
      </h1>
      <p className="county-login__reveal county-login__reveal--subtitle">连接城乡 · 畅通县域 · 服务民生</p>
      <div className="county-login__capabilities county-login__reveal county-login__reveal--features">
        {capabilities.map(({ icon: Icon, title, detail }) => <article key={title}>
          <Icon aria-hidden="true" strokeWidth={1.7} />
          <strong>{title}</strong>
          <small>{detail}</small>
        </article>)}
      </div>
    </div>

    <LogisticsRoute />
    <div className="county-login__freight" aria-hidden="true">
      <Truck />
      <span><strong>智慧物流正在路上</strong><small>干线 · 乡镇 · 村级服务点</small></span>
    </div>
  </section>;
}
