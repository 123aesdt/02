import { Info, X } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";

export type NavigationNoticeState = {
  navigationNotice?: {
    title: string;
    detail: string;
  };
};

export function NavigationNotice() {
  const location = useLocation();
  const navigate = useNavigate();
  const notice = (location.state as NavigationNoticeState | null)?.navigationNotice;

  if (!notice) return null;

  return <aside className="navigation-notice" role="status">
    <Info size={17}/>
    <span><strong>{notice.title}</strong><small>{notice.detail}</small></span>
    <button
      type="button"
      aria-label="关闭提示"
      onClick={() => navigate(`${location.pathname}${location.search}${location.hash}`, { replace: true, state: null })}
    ><X size={16}/></button>
  </aside>;
}
