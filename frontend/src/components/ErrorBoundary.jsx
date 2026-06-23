import { Component } from "react";

export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("QuantLab UI crashed", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="error-boundary">
          <div>
            <span>QuantLab</span>
            <h1>界面加载遇到问题</h1>
            <p>{this.state.error.message || "未知前端异常"}</p>
            <button type="button" onClick={() => window.location.reload()}>刷新页面</button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
