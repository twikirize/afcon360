(function () {
  'use strict';

  var PDF_JS_CDN = 'https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/build/';

  function onReady(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn);
    } else {
      fn();
    }
  }

  onReady(function () {
    var containers = Array.prototype.slice.call(document.querySelectorAll('[data-pdf-src]'));
    if (!containers.length) {
      return;
    }
    var pdfjsLib = window.pdfjsLib;
    if (!pdfjsLib) {
      containers.forEach(function (container) {
        showError(container, 'The PDF viewer could not be loaded. Use the Open or Download buttons above to view this document.');
      });
      return;
    }
    pdfjsLib.GlobalWorkerOptions.workerSrc = PDF_JS_CDN + 'pdf.worker.min.js';
    containers.forEach(function (container) {
      initViewer(container, container.getAttribute('data-pdf-src'));
    });
  });

  function initViewer(container, src) {
    var canvas = container.querySelector('canvas');
    var prevBtn = container.querySelector('[data-pdf-prev]');
    var nextBtn = container.querySelector('[data-pdf-next]');
    var pageLabel = container.querySelector('[data-pdf-pagenum]');
    var pageNum = 1;
    var pdfDoc = null;
    var ctx = null;

    if (!src || !canvas) {
      showError(container, 'No PDF source available.');
      return;
    }
    ctx = canvas.getContext('2d');

    function renderPage(num) {
      pdfDoc.getPage(num).then(function (page) {
        var width = container.clientWidth || canvas.parentElement.clientWidth || 600;
        var base = page.getViewport({ scale: 1 });
        var scale = width / base.width;
        var viewport = page.getViewport({ scale: scale });
        canvas.width = Math.floor(viewport.width);
        canvas.height = Math.floor(viewport.height);
        canvas.style.width = '100%';
        canvas.style.height = 'auto';
        return page.render({ canvasContext: ctx, viewport: viewport }).promise;
      }).then(function () {
        if (pageLabel) {
          pageLabel.textContent = pageNum + ' / ' + pdfDoc.numPages;
        }
        updateButtons();
      }).catch(function () {
        showError(container, 'This PDF could not be rendered in the browser. Use the Open or Download buttons above to view the full document.');
      });
    }

    function updateButtons() {
      if (prevBtn) {
        prevBtn.disabled = pageNum <= 1;
      }
      if (nextBtn) {
        nextBtn.disabled = !pdfDoc || pageNum >= pdfDoc.numPages;
      }
    }

    pdfjsLib.getDocument({
      url: src,
      isEvalSupported: false
    }).promise.then(function (doc) {
      pdfDoc = doc;
      renderPage(pageNum);
    }).catch(function () {
      showError(container, 'This PDF could not be opened. The file may be corrupted or protected. Use the Open or Download buttons above to view it directly.');
    });

    if (prevBtn) {
      prevBtn.addEventListener('click', function () {
        if (pageNum <= 1) {
          return;
        }
        pageNum -= 1;
        renderPage(pageNum);
      });
    }
    if (nextBtn) {
      nextBtn.addEventListener('click', function () {
        if (!pdfDoc || pageNum >= pdfDoc.numPages) {
          return;
        }
        pageNum += 1;
        renderPage(pageNum);
      });
    }
  }

  function showError(container, message) {
    var errorBox = container.querySelector('[data-pdf-error]');
    if (errorBox) {
      errorBox.style.display = 'block';
      errorBox.textContent = message;
    }
    var prevBtn = container.querySelector('[data-pdf-prev]');
    var nextBtn = container.querySelector('[data-pdf-next]');
    var canvas = container.querySelector('canvas');
    if (prevBtn) {
      prevBtn.disabled = true;
    }
    if (nextBtn) {
      nextBtn.disabled = true;
    }
    if (canvas) {
      canvas.style.display = 'none';
    }
  }
})();