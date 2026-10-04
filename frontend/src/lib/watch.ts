import { useCallback, useEffect, useState } from "react";

const KEY = "tenantly.watched";
const UNSEEN = "tenantly.watch.unseen";
const EVT = "tenantly-watch";

export interface WatchEntry {
  address_id: string;
  label: string;
  since: string;
  token?: string;
  atom?: string;
  ics?: string;
}

function read(): WatchEntry[] {
  try {
    return JSON.parse(window.localStorage.getItem(KEY) ?? "[]") as WatchEntry[];
  } catch {
    return [];
  }
}
function write(list: WatchEntry[]) {
  window.localStorage.setItem(KEY, JSON.stringify(list));
  window.dispatchEvent(new Event(EVT));
}

export function useWatched() {
  const [list, setList] = useState<WatchEntry[]>([]);
  const [unseen, setUnseen] = useState(false);
  useEffect(() => {
    const sync = () => {
      setList(read());
      setUnseen(window.localStorage.getItem(UNSEEN) === "1");
    };
    sync();
    window.addEventListener(EVT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(EVT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  const add = useCallback((e: WatchEntry) => {
    const cur = read().filter((x) => x.address_id !== e.address_id);
    write([...cur, e]);
    window.localStorage.setItem(UNSEEN, "1");
    window.dispatchEvent(new Event(EVT));
  }, []);
  const remove = useCallback((id: string) => write(read().filter((x) => x.address_id !== id)), []);
  const markSeen = useCallback(() => {
    window.localStorage.setItem(UNSEEN, "0");
    window.dispatchEvent(new Event(EVT));
  }, []);
  const isWatched = useCallback((id: string) => list.some((x) => x.address_id === id), [list]);

  return { list, unseen, add, remove, markSeen, isWatched };
}
