"use client";

import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";

interface CustomSelectProps {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
}

export function CustomSelect({ label, value, options, onChange }: CustomSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const [coords, setCoords] = useState({ top: 0, left: 0, width: 0 });
  const [openUpwards, setOpenUpwards] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const selectId = useId();
  const labelId = `label-${selectId}`;
  const listboxId = `listbox-${selectId}`;
  const triggerId = `trigger-${selectId}`;

  const updatePosition = () => {
    if (containerRef.current) {
      const triggerRect = containerRef.current.querySelector('.custom-select-trigger')?.getBoundingClientRect();
      
      if (triggerRect) {
        const spaceBelow = window.innerHeight - triggerRect.bottom;
        const needsUpward = spaceBelow < 220;
        setOpenUpwards(needsUpward);
        
        setCoords({
          top: needsUpward ? triggerRect.top : triggerRect.bottom,
          left: triggerRect.left,
          width: triggerRect.width
        });
      }
    }
  };

  useEffect(() => {
    if (isOpen) {
      updatePosition();
      window.addEventListener('scroll', updatePosition, true);
      window.addEventListener('resize', updatePosition);
    }
    return () => {
      window.removeEventListener('scroll', updatePosition, true);
      window.removeEventListener('resize', updatePosition);
    };
  }, [isOpen]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        const dropdown = document.querySelector('.custom-select-dropdown');
        if (dropdown && dropdown.contains(event.target as Node)) return;
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen) {
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') {
        e.preventDefault();
        setIsOpen(true);
        setFocusedIndex(options.findIndex(o => o.value === value));
      }
      return;
    }

    switch (e.key) {
      case 'Escape':
        setIsOpen(false);
        break;
      case 'ArrowDown':
        e.preventDefault();
        setFocusedIndex(prev => (prev < options.length - 1 ? prev + 1 : prev));
        break;
      case 'ArrowUp':
        e.preventDefault();
        setFocusedIndex(prev => (prev > 0 ? prev - 1 : prev));
        break;
      case 'Enter':
      case ' ':
        e.preventDefault();
        if (focusedIndex >= 0) {
          onChange(options[focusedIndex].value);
          setIsOpen(false);
        }
        break;
      case 'Tab':
        setIsOpen(false);
        break;
    }
  };

  useEffect(() => {
    if (!isOpen) setFocusedIndex(-1);
  }, [isOpen]);

  const selectedLabel = options.find(o => o.value === value)?.label || "Select...";

  return (
    <div className="custom-select-container" ref={containerRef}>
      <span className="field-label" id={labelId}>{label}</span>
      <button 
        id={triggerId}
        className="custom-select-trigger" 
        onClick={() => setIsOpen(!isOpen)}
        onKeyDown={handleKeyDown}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-labelledby={`${labelId} ${triggerId}`}
        aria-controls={listboxId}
        aria-activedescendant={focusedIndex >= 0 ? `${selectId}-opt-${focusedIndex}` : undefined}
      >
        <span className="trigger-text">{selectedLabel}</span>
        <svg className={`chevron ${isOpen ? 'open' : ''}`} width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>

      {isOpen && createPortal(
          <div 
            id={listboxId}
            className={`custom-select-dropdown fixed-portal ${openUpwards ? 'upwards' : ''}`}
            role="listbox"
            aria-labelledby={triggerId}
            style={{
              position: 'fixed',
              top: openUpwards ? 'auto' : `${coords.top + 4}px`,
              bottom: openUpwards ? `${window.innerHeight - coords.top + 4}px` : 'auto',
              left: `${coords.left}px`,
              width: `${coords.width}px`,
              zIndex: 9999
            }}
          >
            {options.map((opt, idx) => (
              <div 
                key={opt.value} 
                id={`${selectId}-opt-${idx}`}
                role="option"
                aria-selected={opt.value === value}
                className={`custom-select-option ${opt.value === value ? 'selected' : ''} ${focusedIndex === idx ? 'focused' : ''}`}
                onClick={() => {
                  onChange(opt.value);
                  setIsOpen(false);
                }}
              >
                {opt.label}
              </div>
            ))}
          </div>,
        document.body
      )}
    </div>
  );
}
