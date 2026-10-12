import React from 'react';
import { Loader2 } from 'lucide-react';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'accent' | 'outline' | 'danger' | 'ghost' | 'yellow';
  size?: 'sm' | 'md' | 'lg';
  isLoading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

export const Button: React.FC<ButtonProps> = ({
  children,
  variant = 'primary',
  size = 'md',
  isLoading = false,
  leftIcon,
  rightIcon,
  className = '',
  disabled,
  ...props
}) => {
  const baseClasses =
    'inline-flex items-center justify-center font-medium transition-all duration-150 rounded-lg focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed select-none';

  const sizeClasses = {
    sm: 'text-xs px-2.5 py-1.5 gap-1.5',
    md: 'text-sm px-4 py-2 gap-2',
    lg: 'text-base px-5 py-2.5 gap-2.5',
  };

  const variantClasses = {
    // Primary: Navy Blue #0B1F3A
    primary:
      'bg-aura-navy text-white hover:bg-aura-deep focus:ring-aura-deep shadow-subtle active:scale-[0.99]',
    // Secondary: Deep Blue #123B63
    secondary:
      'bg-aura-deep text-white hover:bg-aura-navy focus:ring-aura-navy shadow-subtle',
    // Accent: Cyan Blue #00B8D9
    accent:
      'bg-aura-cyan text-white hover:bg-aura-cyan-hover focus:ring-aura-cyan shadow-sm',
    // Yellow highlight: #FFC928
    yellow:
      'bg-aura-yellow text-aura-navy hover:bg-yellow-400 font-semibold focus:ring-yellow-500 shadow-sm',
    outline:
      'border border-slate-300 bg-white text-aura-charcoal hover:bg-slate-50 focus:ring-slate-300',
    danger:
      'bg-rose-600 text-white hover:bg-rose-700 focus:ring-rose-500 shadow-sm',
    ghost:
      'text-slate-600 hover:bg-slate-100 hover:text-aura-navy focus:ring-slate-200',
  };

  return (
    <button
      className={`${baseClasses} ${sizeClasses[size]} ${variantClasses[variant]} ${className}`}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? (
        <Loader2 className="w-4 h-4 animate-spin text-current" />
      ) : (
        leftIcon
      )}
      <span>{children}</span>
      {!isLoading && rightIcon}
    </button>
  );
};
