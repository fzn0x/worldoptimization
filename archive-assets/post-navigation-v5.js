(function () {
  var activeIndex = 0;
  var posts = [];

  if ("scrollRestoration" in history) {
    history.scrollRestoration = "manual";
  }

  function refreshPosts() {
    posts = Array.prototype.slice.call(document.querySelectorAll(".archive-post"));
  }

  function isEditableTarget(target) {
    if (!target) return false;
    var tagName = target.tagName;
    return (
      target.isContentEditable ||
      tagName === "INPUT" ||
      tagName === "TEXTAREA" ||
      tagName === "SELECT"
    );
  }

  function scrollToPost(index) {
    if (!posts.length) refreshPosts();
    if (!posts.length) {
      return;
    }

    activeIndex = Math.max(0, Math.min(index, posts.length - 1));
    document.documentElement.dataset.postNavIndex = String(activeIndex);
    var postTop = posts[activeIndex].getBoundingClientRect().top + window.scrollY;
    var targetTop = Math.max(0, postTop - 18);
    window.setTimeout(function () {
      var scroller = document.scrollingElement || document.documentElement;
      scroller.scrollTo({
        top: targetTop,
        behavior: "instant",
      });
    }, 0);
  }

  function nextPostIndex() {
    if (!posts.length) refreshPosts();
    var currentTop = window.scrollY + 24;

    for (var index = 0; index < posts.length; index += 1) {
      var postTop = posts[index].getBoundingClientRect().top + window.scrollY;
      if (postTop > currentTop) return index;
    }

    return posts.length - 1;
  }

  function previousPostIndex() {
    if (!posts.length) refreshPosts();
    var currentTop = window.scrollY - 24;

    for (var index = posts.length - 1; index >= 0; index -= 1) {
      var postTop = posts[index].getBoundingClientRect().top + window.scrollY;
      if (postTop < currentTop) return index;
    }

    return 0;
  }

  document.addEventListener("DOMContentLoaded", refreshPosts);

  window.addEventListener("keydown", function (event) {
    var key = event.key.toLowerCase();
    var isNavigationKey = key === "j" || key === "k" || event.code === "KeyJ" || event.code === "KeyK";

    if (!isNavigationKey) return;

    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) {
      return;
    }
    if (isEditableTarget(event.target)) {
      return;
    }

    event.preventDefault();
    event.stopImmediatePropagation();

    if (key === "j" || event.code === "KeyJ") {
      scrollToPost(nextPostIndex());
    } else if (key === "k" || event.code === "KeyK") {
      scrollToPost(previousPostIndex());
    }
  }, true);
})();
