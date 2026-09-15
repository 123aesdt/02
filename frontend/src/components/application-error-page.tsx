import { AlertTriangle, ArrowLeft, RefreshCw } from "lucide-react";
import { Link, useRouteError } from "react-router-dom";

export function ApplicationErrorPage() {
  useRouteError();

  return <main className="application-error-page" role="alert">
    <section className="application-error-card">
      <span className="application-error-icon" aria-hidden="true"><AlertTriangle size={24}/></span>
      <p className="eyebrow">CountyFlow 运行保护</p>
      <h1>页面暂时无法显示</h1>
      <p>系统已阻止异常继续扩散。调度、救援和维修数据仍由后端持续处理。</p>
      <div className="application-error-actions">
        <button type="button" className="button-primary" onClick={() => window.location.reload()}><RefreshCw size={16}/>重新加载页面</button>
        <Link className="button-secondary" to="/"><ArrowLeft size={16}/>返回工作台</Link>
      </div>
    </section>
  </main>;
}
