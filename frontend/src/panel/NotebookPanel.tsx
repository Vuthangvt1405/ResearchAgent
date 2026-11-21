// The notebook panel inside the page: the page hands it the latest props from the socket and the
// socket's callAction; the panel's own store does the rest.
import { useEffect } from "react";
import { App } from "@/panel/components/App";
import { usePanel } from "@/panel/store";
import type { CallAction, NotebookProps } from "@/panel/types";

export function NotebookPanel({ props, callAction }: { props: NotebookProps | null; callAction: CallAction }): JSX.Element {
  useEffect(() => {
    usePanel.getState().setCallAction(callAction);
  }, [callAction]);
  useEffect(() => {
    if (props) usePanel.getState().setProps(props);
  }, [props]);
  return (
    <div id="rc-panel-root">
      <App />
    </div>
  );
}
