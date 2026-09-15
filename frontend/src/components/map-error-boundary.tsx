import { Component, Fragment, type ReactNode } from "react";
import { MapPinned, RefreshCw } from "lucide-react";

type MapErrorBoundaryProps = {
  children: ReactNode;
  onFallback?: () => void;
};

type MapErrorBoundaryState = {
  failed: boolean;
  recoveryKey: number;
};

export class MapErrorBoundary extends Component<MapErrorBoundaryProps, MapErrorBoundaryState> {
  state: MapErrorBoundaryState = { failed: false, recoveryKey: 0 };

  static getDerivedStateFromError(): Partial<MapErrorBoundaryState> {
    return { failed: true };
  }

  componentDidCatch() {
    this.props.onFallback?.();
  }

  private retry = () => {
    this.setState(({ recoveryKey }) => ({ failed: false, recoveryKey: recoveryKey + 1 }));
  };

  render() {
    if (this.state.failed) {
      return <div className="fleet-map-recovery" role="alert">
        <MapPinned size={18}/>
        <span><strong>地图服务已安全降级</strong><small>本地业务路网仍可查看，调度流程不受影响。</small></span>
        <button type="button" onClick={this.retry}><RefreshCw size={15}/>重新连接高德地图</button>
      </div>;
    }

    return <Fragment key={this.state.recoveryKey}>{this.props.children}</Fragment>;
  }
}
