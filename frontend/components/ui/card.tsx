import * as React from "react"

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "sidebar" | "panel" | "metric" | "composer" | "artifact" | "mini"
}

const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className = "", variant = "panel", children, ...props }, ref) => {
    
    let classes = ""
    if (variant === "sidebar") classes = "sidebar-card"
    else if (variant === "panel") classes = "panel"
    else if (variant === "metric") classes = "metric-card"
    else if (variant === "composer") classes = "composer-card"
    else if (variant === "artifact") classes = "artifact-card"
    else if (variant === "mini") classes = "mini-card"

    return (
      <div ref={ref} className={`${classes} ${className}`} {...props}>
        {/* Adds horizontal scanline effect if applicable, used heavily in the design system */}
        {(variant === "sidebar" || variant === "composer" || variant === "panel") && (
          <div className="scanline-overlay" />
        )}
        {children}
      </div>
    )
  }
)
Card.displayName = "Card"

export { Card }
