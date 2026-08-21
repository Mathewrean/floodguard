const fs = require('fs');
const current = fs.readFileSync('static/css/style.css', 'utf8');
const lines = current.split('\n');

// Check brace balance
let depth = 0;
let inComment = false;
let issues = [];

for (let i = 0; i < lines.length; i++) {
  const line = lines[i];
  const lineNum = i + 1;
  
  // Track comments
  for (let j = 0; j < line.length; j++) {
    if (inComment) {
      if (line.substring(j, j+2) === '*/') {
        inComment = false;
        j += 1;
      }
    } else {
      if (line.substring(j, j+2) === '/*') {
        inComment = true;
        j += 1;
      }
    }
  }
  
  if (!inComment) {
    const opens = (line.match(/{/g) || []).length;
    const closes = (line.match(/}/g) || []).length;
    depth += opens - closes;
  }
  
  if (depth < 0) {
    issues.push('Negative depth at line ' + lineNum);
    depth = 0;
  }
}

console.log('Current CSS - Final depth:', depth, 'Issues:', issues.length);
console.log('Total lines:', lines.length);
issues.slice(0, 30).forEach(i => console.log(i));

// Also verify all selectors from a known good list exist
const selectors = [
  '.dashboard-sidebar',
  '.dashboard-nav-toggle',
  '.sidebar-toggle',
  '.nav-menu',
  '.nav-menu a',
  '.gis-left-panel',
  '.search-bar',
  '.search-results',
  '.dashboard-content',
  '.dashboard-nav-open',
  '.dashboard-controlbar'
];
selectors.forEach(sel => {
  const found = current.includes(sel);
  if (!found) console.log('MISSING:', sel);
});
