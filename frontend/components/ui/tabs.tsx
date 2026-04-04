import * as React from "react"

export interface TabsProps<T extends string> {
  tabs: readonly T[];
  activeTab: T;
  onChange: (tab: T) => void;
  className?: string;
}

export function Tabs<T extends string>({ tabs, activeTab, onChange, className = "" }: TabsProps<T>) {
  const handleKeyDown = (e: React.KeyboardEvent, index: number) => {
    if (e.key === 'ArrowRight') {
      const nextIndex = (index + 1) % tabs.length;
      onChange(tabs[nextIndex]);
      (e.currentTarget.parentElement?.children[nextIndex] as HTMLElement)?.focus();
    } else if (e.key === 'ArrowLeft') {
      const prevIndex = (index - 1 + tabs.length) % tabs.length;
      onChange(tabs[prevIndex]);
      (e.currentTarget.parentElement?.children[prevIndex] as HTMLElement)?.focus();
    }
  };

  return (
    <div className={`tab-bar ${className}`} role="tablist">
      {tabs.map((tab, idx) => (
        <button
          key={tab}
          id={`tab-${tab}`}
          className={tab === activeTab ? "tab-button active" : "tab-button"}
          onClick={() => onChange(tab)}
          onKeyDown={(e) => handleKeyDown(e, idx)}
          role="tab"
          aria-selected={tab === activeTab}
          aria-controls={`panel-${tab}`}
          tabIndex={tab === activeTab ? 0 : -1}
        >
          {tab}
        </button>
      ))}
    </div>
  )
}
