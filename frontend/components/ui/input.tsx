import * as React from "react"

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className = "", label, ...props }, ref) => {
    return (
      <div className="form-section">
        {label && <label className="field-label">{label}</label>}
        <input
          ref={ref}
          className={`sidebar-textarea select-field ${className}`} /* Reusing textarea/select styles for input */
          {...props}
        />
      </div>
    )
  }
)
Input.displayName = "Input"

export { Input }
