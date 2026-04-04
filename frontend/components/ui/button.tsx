import * as React from "react"

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost"
  size?: "default" | "large"
  isLoading?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className = "", variant = "primary", size = "default", isLoading, children, disabled, ...props }, ref) => {
    
    let classes = ""
    if (variant === "primary") classes = "primary-button"
    else if (variant === "secondary") classes = "secondary-button"
    else if (variant === "ghost") classes = "ghost-button"

    if (size === "large") classes += " large"

    return (
      <button
        ref={ref}
        className={`${classes} ${className}`}
        disabled={disabled || isLoading}
        aria-busy={isLoading}
        {...props}
      >
        {isLoading ? "Processing..." : children}
      </button>
    )
  }
)
Button.displayName = "Button"

export { Button }
