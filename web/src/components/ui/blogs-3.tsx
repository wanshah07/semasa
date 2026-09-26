/* The "blogs-3" card grid (pasted by Wan on 27 Sep 2026). In Semasa it is the Wangian gallery of saved designs
   (pages/FragranceTab.jsx); the demo data below stays as the default so BlogsSection alone still shows the original.
   Changed for Semasa, and why:
   - `blogs`, `title`, `description`, `ratio`, `imageClassName`, `target`, `empty` and `by` are props (the original was
     hard-wired to its demo list);
   - the demo pictures are Unsplash photographs (images.unsplash.com), not the 21st.dev CDN, and the fallback is a
     small inline picture, so nothing depends on a host we do not control;
   - `outline-offset-[3px]` (Tailwind 3 has no `outline-offset-3`), and the unknown `cn-rounded` became rounded-lg;
   - the hover uses bg-muted, which tailwind.config.js points at the theme's pale surface for backgrounds only. */
import type * as React from "react";
import { cn } from "@/lib/utils";
import { FullWidthDivider } from "@/components/ui/blogs-3-utils/full-width-divider";
import { LazyImage } from "@/components/ui/lazy-image";

export type BlogType = {
  title: string;
  href: string;
  description: string;
  author: string;
  createdAt: string;
  readTime: string;
  image: string;
};

const FALLBACK =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 9"><rect width="16" height="9" fill="#e5e7eb"/>' +
      '<path d="M5 6.5l2-2.5 1.5 1.8L10 4l2 2.5z" fill="#9ca3af"/><circle cx="6" cy="3" r=".8" fill="#9ca3af"/></svg>',
  );

const blogs: BlogType[] = [
  {
    title: "Design Systems That Scale",
    href: "#",
    description:
      "Learn how to build and maintain scalable design systems that empower teams to move faster while staying consistent.",
    image: "https://images.unsplash.com/photo-1756723902378-7073227e8ece?auto=format&fit=crop&w=800&q=80",
    createdAt: "2025-08-25",
    author: "Ava Mitchell",
    readTime: "7 min read",
  },
  {
    title: "The Psychology of Color in UI",
    href: "#",
    description:
      "Explore how different colors influence user perception, emotion, and conversion in digital product design.",
    image: "https://images.unsplash.com/photo-1695712551846-4dc15433fbd4?auto=format&fit=crop&w=800&q=80",
    createdAt: "2025-07-14",
    author: "Liam Carter",
    readTime: "5 min read",
  },
  {
    title: "Microinteractions That Delight",
    href: "#",
    description:
      "Discover how subtle animations and interactions can enhance usability and bring joy to your users.",
    image: "https://images.unsplash.com/photo-1626196607758-266f19558d3f?auto=format&fit=crop&w=800&q=80",
    createdAt: "2025-06-30",
    author: "Sophia Kim",
    readTime: "6 min read",
  },
  {
    title: "Accessibility Beyond Compliance",
    href: "#",
    description:
      "Practical steps to make your UI accessible, not just legally compliant, but genuinely inclusive for everyone.",
    image: "https://images.unsplash.com/photo-1647790292957-c7f3b44b3973?auto=format&fit=crop&w=800&q=80",
    createdAt: "2025-06-18",
    author: "Ethan Rodriguez",
    readTime: "8 min read",
  },
  {
    title: "Dark Mode Done Right",
    href: "#",
    description:
      "Tips and tricks to design beautiful and functional dark mode experiences that users will love.",
    image: "https://images.unsplash.com/photo-1715593949273-09009558300a?auto=format&fit=crop&w=800&q=80",
    createdAt: "2025-05-20",
    author: "Maya Chen",
    readTime: "4 min read",
  },
  {
    title: "Typography That Speaks",
    href: "#",
    description:
      "How to select and pair typefaces that enhance readability, hierarchy, and brand personality.",
    image: "https://images.unsplash.com/photo-1716703371653-ca74beaa7a4a?auto=format&fit=crop&w=800&q=80",
    createdAt: "2025-05-02",
    author: "Noah Patel",
    readTime: "9 min read",
  },
  {
    title: "The Future of UI Animation",
    href: "#",
    description:
      "From motion guidelines to advanced prototyping—discover where UI animation is headed in 2025.",
    image: "https://images.unsplash.com/photo-1716703373020-17ff360924ee?auto=format&fit=crop&w=800&q=80",
    createdAt: "2025-04-15",
    author: "Chloe Ramirez",
    readTime: "10 min read",
  },
  {
    title: "Minimalism vs Maximalism",
    href: "#",
    description:
      "A deep dive into two opposing design philosophies and how to decide which fits your product.",
    image: "https://images.unsplash.com/photo-1715593949345-50d3304cff4b?auto=format&fit=crop&w=800&q=80",
    createdAt: "2025-04-01",
    author: "Benjamin Scott",
    readTime: "6 min read",
  },
  {
    title: "Designing for Mobile-First",
    href: "#",
    description:
      "Best practices for mobile-first design, from layout decisions to performance optimization.",
    image: "https://images.unsplash.com/photo-1715593948040-d013495c3647?auto=format&fit=crop&w=800&q=80",
    createdAt: "2025-03-22",
    author: "Isabella White",
    readTime: "7 min read",
  },
  {
    title: "Figma Hacks for Power Users",
    href: "#",
    description:
      "Hidden features, shortcuts, and workflows in Figma that can dramatically speed up your design process.",
    image: "https://images.unsplash.com/photo-1625232480886-f0c38e7a6a5e?auto=format&fit=crop&w=800&q=80",
    createdAt: "2025-03-09",
    author: "James Walker",
    readTime: "5 min read",
  },
  {
    title: "Designing With AI Tools",
    href: "#",
    description:
      "A practical look at how AI tools are shaping UI/UX workflows—from ideation to final delivery.",
    image: "https://images.unsplash.com/photo-1761123261084-53c40fe1e607?auto=format&fit=crop&w=800&q=80",
    createdAt: "2025-02-28",
    author: "Olivia Brooks",
    readTime: "8 min read",
  },
  {
    title: "The Art of Prototyping",
    href: "#",
    description:
      "How to create prototypes that effectively communicate your ideas and speed up stakeholder feedback.",
    image: "https://images.unsplash.com/photo-1782290547018-8bb89b8edf07?auto=format&fit=crop&w=800&q=80",
    createdAt: "2025-02-14",
    author: "Daniel Green",
    readTime: "6 min read",
  },
];

export function BlogsSection({
  blogs: list = blogs,
  title = "Blog Section",
  description = "Discover the latest trends and insights in the world of design and technology.",
  ratio = 16 / 9,
  imageClassName,
  target,
  empty,
  by = "by",
  className,
}: {
  blogs?: BlogType[];
  title?: React.ReactNode;
  description?: React.ReactNode;
  ratio?: number;
  imageClassName?: string;
  target?: string;
  empty?: React.ReactNode;
  /** the word before the author ("by"; Semasa passes "oleh" in BM) */
  by?: string;
  className?: string;
}) {
  return (
    <div className={cn("mx-auto w-full max-w-5xl grow", className)}>
      <div className="space-y-1 px-4 py-8 md:px-6">
        <h1 className="font-semibold text-2xl tracking-wide md:text-4xl">
          {title}
        </h1>
        <p className="text-muted-foreground text-sm md:text-base">
          {description}
        </p>
      </div>
      <FullWidthDivider contained={true} />
      {list.length === 0 && empty ? (
        <div className="p-8 text-center text-muted-foreground text-sm">{empty}</div>
      ) : (
        <div className="z-10 grid p-4 md:grid-cols-2 lg:grid-cols-3">
          {list.map((blog) => (
            <BlogCard
              {...blog}
              key={blog.href + blog.title}
              ratio={ratio}
              imageClassName={imageClassName}
              target={target}
              by={by}
              rel={target === "_blank" ? "noopener noreferrer" : undefined}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function BlogCard({
  title,
  description,
  createdAt,
  readTime,
  image,
  author,
  ratio = 16 / 9,
  imageClassName,
  by = "by",
  className,
  ...props
}: React.ComponentProps<"a"> & BlogType & { ratio?: number; imageClassName?: string; by?: string }) {
  return (
    <a
      className={cn(
        "rounded-lg group flex flex-col gap-2 p-3 hover:bg-muted/50 active:bg-muted",
        className,
      )}
      {...props}
    >
      <LazyImage
        alt={title}
        className={cn("transition-all duration-500 group-hover:scale-105", imageClassName)}
        containerClassName="rounded-lg shadow-md outline outline-offset-[3px] outline-border/50"
        fallback={FALLBACK}
        inView={true}
        ratio={ratio}
        src={image}
      />
      <div className="space-y-2 px-2 pb-2">
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground group-hover:text-foreground sm:text-xs">
          <p>{by} {author}</p>
          <div className="size-1 rounded-full bg-muted-foreground" />
          <p>{createdAt}</p>
          <div className="size-1 rounded-full bg-muted-foreground" />
          <p>{readTime}</p>
        </div>
        <h2 className="line-clamp-2 font-semibold text-lg">{title}</h2>
        <p className="line-clamp-3 text-muted-foreground text-sm group-active:text-foreground">
          {description}
        </p>
      </div>
    </a>
  );
}

export default BlogsSection;
