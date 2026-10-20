export type RatedReview = {rating: number | null; source: string | null};

export function reviewRatingScale(source: string | null | undefined): 5 | 10 {
  const normalized = (source || '').trim().toLocaleLowerCase('it-IT');
  return normalized === 'google' || normalized === 'tripadvisor' ? 5 : 10;
}

export function normalizedReviewRating(review: RatedReview): number | null {
  if (review.rating === null || !Number.isFinite(review.rating)) return null;
  return review.rating / reviewRatingScale(review.source) * 10;
}

export function reviewRatingTone(review: RatedReview): 'positive' | 'negative' | 'unrated' {
  const normalized = normalizedReviewRating(review);
  if (normalized === null) return 'unrated';
  return normalized >= 6 ? 'positive' : 'negative';
}
