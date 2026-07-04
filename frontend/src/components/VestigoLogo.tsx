import Image from "next/image";

type VestigoLogoProps = {
  size?: number;
  className?: string;
};

/**
 * Vestigo brand mark - the owl logo, a nod to the name (Latin: "I track / trace").
 * Served from /public/vestigo-owl.png. Reused in the sidebar wordmark and the
 * Chat With Stock empty state.
 */
export function VestigoLogo({ size = 30, className }: VestigoLogoProps) {
  return (
    <Image
      src="/icon.png"
      alt="Vestigo"
      width={size}
      height={size}
      className={className}
      unoptimized
      style={{ height: "auto", objectFit: "contain", background: "transparent" }}
    />
  );
}
