import { getCollection } from 'astro:content';
import siteConfig from '../data/site.config.json';
import cloudResources from '../data/cloud-resources.json';
import { resourceSearchEntry } from '../lib/search.mjs';
import {
  formatDate,
  getPostCategory,
  getPostExcerpt,
  getPostPath,
  getPostTags,
  sortPosts,
} from '../lib/posts';

export async function GET() {
  const posts = sortPosts(await getCollection('posts'));
  const items = posts.map((post) => {
    const category = getPostCategory(post);
    const tags = getPostTags(post);
    const keywords = post.data.keywords ?? [];
    // Real excerpt only — the generic filler would both clutter result rows
    // and make every post match queries like "笔记".
    const description = getPostExcerpt(post) ?? '';

    return {
      kind: 'post',
      title: post.data.title,
      description,
      url: getPostPath(post),
      date: post.data.date ? formatDate(post.data.date) : '',
      category: category ?? '',
      tags,
      keywords,
      text: [
        post.data.title,
        description,
        category,
        ...tags,
        ...keywords,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase(),
    };
  });

  const resources = [...cloudResources, ...siteConfig.projectGroups[0].items].map(resourceSearchEntry);

  return new Response(JSON.stringify([...resources, ...items]), {
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
    },
  });
}
