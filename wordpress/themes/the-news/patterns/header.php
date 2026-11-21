<?php
/**
 * Title: 머리글
 * Slug: the-news/header
 * Categories: header
 * Inserter: no
 */
?>
<!-- wp:group {"tagName":"header","className":"tn-header","layout":{"type":"constrained","contentSize":"1080px"}} -->
<header class="wp-block-group tn-header">
<!-- wp:group {"className":"tn-header-in","layout":{"type":"flex","orientation":"vertical","flexWrap":"nowrap"}} -->
<div class="wp-block-group tn-header-in">
<!-- wp:html -->
<a class="tn-logo" href="<?php echo esc_url( home_url( '/' ) ); ?>" rel="home"><img src="<?php echo esc_url( get_theme_file_uri( 'assets/images/logo.png' ) ); ?>" alt="<?php echo esc_attr( get_bloginfo( 'name' ) ); ?>" width="1200" height="241"></a>
<!-- /wp:html -->
<!-- wp:group {"tagName":"nav","className":"tn-cats","ariaLabel":"분류","layout":{"type":"flex","flexWrap":"wrap"}} -->
<nav class="wp-block-group tn-cats" aria-label="분류">
<!-- wp:html -->
<a class="tn-cats-all" href="<?php echo esc_url( home_url( '/' ) ); ?>">전체</a>
<!-- /wp:html -->
<!-- wp:categories {"showPostCounts":false,"showEmpty":false,"className":"tn-cats-list"} /-->
</nav>
<!-- /wp:group -->
</div>
<!-- /wp:group -->
</header>
<!-- /wp:group -->
