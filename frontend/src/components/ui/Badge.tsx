import React from 'react';

export interface BadgeProps {
  children: React.ReactNode;
  variant?:
    | 'active'
    | 'archived'
    | 'draft'
    | 'disabled'
    | 'pending'
    | 'approved'
    | 'applied'
    | 'rejected'
    | 'stale'
    | 'failed'
    | 'cyan'
    | 'navy'
    | 'neutral';
  size?: 'sm' | 'md';
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'neutral',
  size = 'md',
  className = '',
}) => {
  const sizeClasses = {
    sm: 'text-[10px] px-2 py-0.5 font-medium',
    md: 'text-xs px-2.5 py-1 font-semibold',
  };

  const variantClasses: Record<string, string> = {
    // Active / Success green #22C55E
    active: 'bg-emerald-50 text-emerald-700 border border-emerald-200',
    archived: 'bg-slate-100 text-slate-500 border border-slate-200',
    applied: 'bg-emerald-100 text-emerald-800 border border-emerald-300 font-semibold',
    // Pending / Yellow highlight #FFC928
    pending: 'bg-amber-50 text-amber-800 border border-amber-300 font-semibold',
    // Approved / Cyan
    approved: 'bg-cyan-50 text-cyan-800 border border-cyan-300 font-semibold',
    // Draft
    draft: 'bg-slate-100 text-slate-700 border border-slate-300',
    // Rejected / Failed
    rejected: 'bg-rose-50 text-rose-700 border border-rose-200',
    failed: 'bg-red-100 text-red-800 border border-red-300',
    stale: 'bg-orange-50 text-orange-700 border border-orange-200',
    disabled: 'bg-gray-100 text-gray-500 border border-gray-200',
    cyan: 'bg-cyan-50 text-aura-cyan border border-cyan-200',
    navy: 'bg-aura-navy text-white',
    neutral: 'bg-slate-100 text-slate-700 border border-slate-200',
  };

  const variantClass = variantClasses[variant] || variantClasses.neutral;

  return (
    <span
      className={`inline-flex items-center rounded-full tracking-wide uppercase ${sizeClasses[size]} ${variantClass} ${className}`}
    >
      {children}
    </span>
  );
};
