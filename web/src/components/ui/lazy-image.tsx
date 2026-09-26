'use client';

/* efferd's LazyImage. Changed for Semasa, and why:
   - `containerClassName` is accepted as well as `AspectRatioClassName`: blogs-3 passes the former, which the original
     silently dropped (a TypeScript error in the paste);
   - the skeleton is bg-secondary: in Semasa `accent` is the brand colour, not shadcn's pale grey;
   - `[transition-duration:2000ms]`: Tailwind 3 has no `duration-2000`;
   - `fetchPriority` is passed lower-case, which is the attribute React 18 knows. */
import React from 'react';
import { cn } from '@/lib/utils';
import { useInView } from 'framer-motion';
import { AspectRatio } from '@/components/ui/aspect-ratio';

interface LazyImageProps {
	alt: string;
	src: string;
	className?: string;
	AspectRatioClassName?: string;
	/** the same as AspectRatioClassName (the name blogs-3 uses) */
	containerClassName?: string;
	/** URL of the fallback image. default: undefined */
	fallback?: string;
	/** The ratio of the image. */
	ratio: number;
	/** Whether the image should only load when it is in view. default: false */
	inView?: boolean;
}

export function LazyImage({
	alt,
	src,
	ratio,
	fallback,
	inView = false,
	className,
	AspectRatioClassName,
	containerClassName,
}: LazyImageProps) {
	const ref = React.useRef<HTMLDivElement | null>(null);
	const imgRef = React.useRef<HTMLImageElement | null>(null);
	const isInView = useInView(ref, { once: true });

	const [imgSrc, setImgSrc] = React.useState<string | undefined>(
		inView ? undefined : src,
	);
	const [isLoading, setIsLoading] = React.useState(true);

	const handleError = () => {
		if (fallback && imgSrc !== fallback) {
			setImgSrc(fallback);
			return;
		}
		setIsLoading(false);
	};

	const handleLoad = () => {
		setIsLoading(false);
	};

	// Load image only when inView
	React.useEffect(() => {
		if (inView && isInView && !imgSrc) {
			setImgSrc(src);
		}
	}, [inView, isInView, src, imgSrc]);

	// Handle cached images instantly
	React.useEffect(() => {
		if (imgRef.current && imgRef.current.complete && imgRef.current.naturalWidth > 0) {
			handleLoad();
		}
	}, [imgSrc]);

	return (
		<AspectRatio
			ref={ref}
			ratio={ratio}
			className={cn(
				'relative size-full overflow-hidden rounded-lg border',
				AspectRatioClassName,
				containerClassName,
			)}
		>
			{/* Skeleton / fallback */}
			<div
				className={cn(
					'bg-secondary absolute inset-0 animate-pulse rounded-lg transition-opacity will-change-[opacity]',
					{ 'opacity-0': !isLoading },
				)}
			/>

			{imgSrc && (
				<img
					ref={imgRef}
					alt={alt}
					src={imgSrc}
					className={cn(
						'size-full rounded-lg object-cover opacity-0 transition-opacity [transition-duration:2000ms] will-change-[opacity]',
						{
							'opacity-100': !isLoading,
						},
						className,
					)}
					onLoad={handleLoad}
					onError={handleError}
					loading="lazy"
					decoding="async"
					{...{ fetchpriority: inView ? 'high' : 'low' }}
				/>
			)}
		</AspectRatio>
	);
}
