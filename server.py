#!/usr/bin/env python3
import http.server
import socketserver
import json
import re
import os
import tempfile
from urllib.parse import parse_qs, urlparse

# Try to import PDF and DOCX support
try:
    import PyPDF2
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    print("Warning: PyPDF2 not installed. PDF files won't work.")
    print("Install with: pip install PyPDF2")

try:
    import docx
    DOCX_SUPPORT = True
except ImportError:
    DOCX_SUPPORT = False
    print("Warning: python-docx not installed. DOCX files won't work.")
    print("Install with: pip install python-docx")

class ResumeHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.path = '/index.html'
        return http.server.SimpleHTTPRequestHandler.do_GET(self)
    
    def do_POST(self):
        if self.path == '/upload':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            # Parse multipart form data
            boundary = self.headers['Content-Type'].split('boundary=')[1].encode()
            parts = post_data.split(b'--' + boundary)
            
            job_description = ""
            files_data = []
            
            for part in parts:
                if b'Content-Disposition' in part:
                    if b'name="job_description"' in part:
                        text_start = part.find(b'\r\n\r\n') + 4
                        job_description = part[text_start:].decode('utf-8', errors='ignore').strip()
                    
                    elif b'name="resumes"' in part and b'filename=' in part:
                        text_start = part.find(b'\r\n\r\n') + 4
                        file_content = part[text_start:]
                        
                        filename_start = part.find(b'filename="') + 10
                        filename_end = part.find(b'"', filename_start)
                        filename = part[filename_start:filename_end].decode()
                        
                        files_data.append({
                            'name': filename,
                            'content': file_content
                        })
            
            # Process the resumes
            results = self.process_resumes(job_description, files_data)
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(results).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def extract_text_from_pdf(self, content):
        if not PDF_SUPPORT:
            return ""
        try:
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
            temp_file.write(content)
            temp_file.close()
            
            with open(temp_file.name, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                text = ""
                for page in reader.pages:
                    text += page.extract_text()
            os.unlink(temp_file.name)
            return text
        except Exception as e:
            print(f"PDF parsing error: {e}")
            return ""
    
    def extract_text_from_docx(self, content):
        if not DOCX_SUPPORT:
            return ""
        try:
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.docx')
            temp_file.write(content)
            temp_file.close()
            
            doc = docx.Document(temp_file.name)
            text = "\n".join([para.text for para in doc.paragraphs])
            os.unlink(temp_file.name)
            return text
        except Exception as e:
            print(f"DOCX parsing error: {e}")
            return ""
    
    def extract_requirements(self, jd_text):
        """Extract requirements from job description with more detail"""
        jd_lower = jd_text.lower()
        
        # Degrees with variations
        degree_patterns = {
            "Bachelor's Degree": ['bachelor', 'b.tech', 'b.e', 'b.sc', 'ba', 'bca'],
            "Master's Degree": ['master', 'm.tech', 'm.e', 'm.sc', 'mba', 'mca'],
            "PhD": ['phd', 'doctorate', 'doctoral']
        }
        
        found_degrees = []
        for degree_level, keywords in degree_patterns.items():
            if any(keyword in jd_lower for keyword in keywords):
                found_degrees.append(degree_level)
        
        # Experience
        exp_match = re.search(r'(\d+)[\+ ]? years?', jd_lower)
        min_exp = int(exp_match.group(1)) if exp_match else 0
        
        # Skills with categories
        skill_categories = {
            'Programming Languages': ['python', 'java', 'javascript', 'c++', 'c#', 'ruby', 'go', 'rust'],
            'Web Technologies': ['react', 'angular', 'vue', 'node.js', 'html', 'css', 'django', 'flask'],
            'Databases': ['sql', 'mysql', 'postgresql', 'mongodb', 'oracle', 'redis'],
            'Cloud & DevOps': ['aws', 'azure', 'gcp', 'docker', 'kubernetes', 'jenkins', 'git'],
            'Data & Analytics': ['excel', 'tableau', 'power bi', 'spark', 'hadoop', 'pandas']
        }
        
        required_skills = []
        for category, skills in skill_categories.items():
            for skill in skills:
                if skill in jd_lower:
                    required_skills.append({'name': skill, 'category': category})
        
        # Extract specific requirements
        specific_requirements = []
        
        # Check for certification requirements
        if 'certified' in jd_lower or 'certification' in jd_lower:
            specific_requirements.append("Certification required")
        
        # Check for specific tools
        tools = ['excel', 'tableau', 'power bi', 'salesforce', 'sap']
        for tool in tools:
            if tool in jd_lower:
                specific_requirements.append(f"Experience with {tool}")
        
        return {
            'degrees': found_degrees,
            'experience': min_exp,
            'skills': required_skills,
            'specific_requirements': specific_requirements
        }
    
    def check_candidate(self, resume_text, requirements, filename):
        """Check if candidate meets requirements with detailed reasons"""
        resume_lower = resume_text.lower()
        missing = []
        matched = []
        details = {
            'found_degree': None,
            'found_experience': 0,
            'found_skills': [],
            'missing_skills': [],
            'certifications': []
        }
        
        # Check degree with specific findings
        if requirements['degrees']:
            found_any_degree = False
            found_degree_name = None
            
            for req_degree in requirements['degrees']:
                if req_degree == "Bachelor's Degree":
                    patterns = ['bachelor', 'b.tech', 'b.e', 'b.sc', 'ba', 'bca']
                    for pattern in patterns:
                        if pattern in resume_lower:
                            found_any_degree = True
                            found_degree_name = pattern.upper()
                            break
                elif req_degree == "Master's Degree":
                    patterns = ['master', 'm.tech', 'm.e', 'm.sc', 'mba', 'mca']
                    for pattern in patterns:
                        if pattern in resume_lower:
                            found_any_degree = True
                            found_degree_name = pattern.upper()
                            break
                elif req_degree == "PhD":
                    if 'phd' in resume_lower or 'doctorate' in resume_lower:
                        found_any_degree = True
                        found_degree_name = "PhD"
            
            if found_any_degree:
                matched.append(f"✓ Degree: {found_degree_name}")
                details['found_degree'] = found_degree_name
            else:
                missing.append(f"✗ Degree: {', '.join(requirements['degrees'])} required")
                details['missing_degree'] = requirements['degrees']
        
        # Check experience with details
        if requirements['experience'] > 0:
            exp_match = re.search(r'(\d+)[\+ ]? years?', resume_lower)
            exp = int(exp_match.group(1)) if exp_match else 0
            details['found_experience'] = exp
            
            if exp >= requirements['experience']:
                matched.append(f"✓ Experience: {exp} years (Need {requirements['experience']}+)")
            else:
                missing.append(f"✗ Experience: Only {exp} years (Need {requirements['experience']}+ years)")
        
        # Check skills with categorization
        if requirements['skills']:
            found_skills = []
            missing_skills = []
            
            for skill in requirements['skills']:
                if skill['name'] in resume_lower:
                    found_skills.append(skill)
                    details['found_skills'].append(skill['name'])
                else:
                    missing_skills.append(skill)
                    details['missing_skills'].append(skill['name'])
            
            if found_skills:
                skill_names = [s['name'] for s in found_skills]
                matched.append(f"✓ Skills: Found {len(found_skills)}/{len(requirements['skills'])} ({', '.join(skill_names[:3])})")
            
            if missing_skills:
                missing_skill_names = [s['name'] for s in missing_skills]
                if len(missing_skills) > 0:
                    missing.append(f"✗ Missing Skills: {', '.join(missing_skill_names[:5])}")
        
        # Check for certifications
        cert_keywords = ['certified', 'certification', 'aws certified', 'pmp', 'scrum', 'azure']
        found_certs = [cert for cert in cert_keywords if cert in resume_lower]
        if found_certs:
            details['certifications'] = found_certs
            matched.append(f"✓ Certifications: {', '.join(found_certs[:2])}")
        
        # Calculate score with weighted importance
        score = 100
        if missing:
            # Deduct points based on missing requirements
            deduction_per_missing = 100 / (len(missing) + len(requirements['degrees']) + 1)
            score = max(0, 100 - (len(missing) * 25) - (len(details.get('missing_skills', [])) * 5))
        
        # Generate overall rejection reason
        rejection_reason = None
        if missing:
            if any('Degree' in m for m in missing):
                rejection_reason = "Does not meet educational requirements"
            elif any('Experience' in m for m in missing):
                rejection_reason = f"Insufficient experience (has {details['found_experience']} years, needs {requirements['experience']}+)"
            elif any('Skills' in m for m in missing):
                missing_count = len(details.get('missing_skills', []))
                rejection_reason = f"Missing {missing_count} required technical skills"
            else:
                rejection_reason = "Does not meet minimum qualifications"
        
        return {
            'filename': filename,
            'qualified': len(missing) == 0,
            'score': max(0, min(100, score)),
            'missing': missing,
            'matched': matched,
            'details': details,
            'rejection_reason': rejection_reason,
            'recommendation': self.get_recommendation(missing, details, requirements)
        }
    
    def get_recommendation(self, missing, details, requirements):
        """Generate actionable recommendations for the candidate"""
        if not missing:
            return None
        
        recommendations = []
        
        # Degree recommendation
        if any('Degree' in m for m in missing):
            recommendations.append("Consider pursuing the required degree or gaining equivalent experience")
        
        # Experience recommendation
        if any('Experience' in m for m in missing):
            needed = requirements['experience'] - details['found_experience']
            recommendations.append(f"Gain {needed} more years of relevant experience")
        
        # Skills recommendation
        if details.get('missing_skills'):
            missing_skills = details['missing_skills'][:3]
            recommendations.append(f"Learn missing skills: {', '.join(missing_skills)}")
        
        # Certification recommendation
        if requirements.get('specific_requirements') and 'certification' in str(requirements['specific_requirements']).lower():
            recommendations.append("Consider obtaining relevant certifications")
        
        return recommendations[:3]  # Return top 3 recommendations
    
    def process_resumes(self, job_description, files_data):
        """Process all uploaded resumes"""
        if not job_description:
            return {'error': 'No job description provided'}
        
        requirements = self.extract_requirements(job_description)
        results = []
        
        for file_data in files_data:
            filename = file_data['name']
            content = file_data['content']
            
            # Extract text based on file type
            if filename.endswith('.pdf'):
                text = self.extract_text_from_pdf(content)
            elif filename.endswith('.docx'):
                text = self.extract_text_from_docx(content)
            else:
                try:
                    text = content.decode('utf-8', errors='ignore')
                except:
                    text = ""
            
            if text:
                result = self.check_candidate(text, requirements, filename)
                results.append(result)
            else:
                results.append({
                    'filename': filename,
                    'qualified': False,
                    'score': 0,
                    'missing': ['Could not parse file content'],
                    'matched': [],
                    'details': {},
                    'rejection_reason': 'File could not be parsed or is corrupted',
                    'recommendation': ['Please upload a valid PDF, DOCX, or TXT file']
                })
        
        # Sort by score
        results.sort(key=lambda x: x['score'], reverse=True)
        
        # Calculate stats
        qualified_count = len([r for r in results if r['qualified']])
        
        return {
            'success': True,
            'results': results,
            'stats': {
                'total': len(results),
                'qualified': qualified_count,
                'not_qualified': len(results) - qualified_count,
                'avg_score': sum(r['score'] for r in results) / len(results) if results else 0
            },
            'job_requirements': {
                'required_degree': requirements['degrees'],
                'min_experience': requirements['experience'],
                'required_skills': [s['name'] for s in requirements['skills']],
                'total_requirements': len(requirements['degrees']) + (1 if requirements['experience'] > 0 else 0) + len(requirements['skills'])
            }
        }

# HTML Content with detailed rejection reasons display
HTML_CONTENT = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Resume Shortlister - Smart Rejection Reasons</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        h1 { color: #333; margin-bottom: 10px; }
        .subtitle { color: #666; margin-bottom: 30px; }
        .section { margin-bottom: 25px; }
        .section-title { font-size: 18px; font-weight: 600; margin-bottom: 10px; color: #333; }
        textarea {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-family: monospace;
            font-size: 14px;
            resize: vertical;
        }
        textarea:focus { outline: none; border-color: #667eea; }
        .upload-area {
            border: 2px dashed #667eea;
            border-radius: 8px;
            padding: 30px;
            text-align: center;
            background: #f8f9ff;
            cursor: pointer;
            transition: all 0.3s;
        }
        .upload-area:hover { background: #f0f2ff; }
        .file-list { margin-top: 15px; }
        .file-tag {
            background: #667eea;
            color: white;
            padding: 5px 12px;
            border-radius: 20px;
            display: inline-block;
            margin: 5px;
            font-size: 12px;
        }
        .remove-file {
            cursor: pointer;
            margin-left: 8px;
            font-weight: bold;
        }
        button {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 12px 30px;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            width: 100%;
            margin-top: 20px;
        }
        button:hover { transform: translateY(-2px); }
        button:disabled { opacity: 0.6; cursor: not-allowed; }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px;
            border-radius: 10px;
            text-align: center;
        }
        .stat-number { font-size: 28px; font-weight: bold; }
        .result-card {
            border: 1px solid #e0e0e0;
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 15px;
            cursor: pointer;
            transition: all 0.3s;
        }
        .result-card:hover { transform: translateX(5px); }
        .qualified { background: #d4edda; border-left: 4px solid #28a745; }
        .not-qualified { background: #f8d7da; border-left: 4px solid #dc3545; }
        .result-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; }
        .score {
            font-size: 20px;
            font-weight: bold;
            padding: 5px 10px;
            border-radius: 50px;
            background: white;
        }
        .details-content {
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #ddd;
            display: none;
        }
        .details-content.show { display: block; }
        .missing-list { color: #dc3545; margin: 10px 0; }
        .matched-list { color: #28a745; margin: 10px 0; }
        .rejection-box {
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 12px;
            margin: 10px 0;
            border-radius: 5px;
        }
        .recommendation-box {
            background: #d1ecf1;
            border-left: 4px solid #17a2b8;
            padding: 12px;
            margin: 10px 0;
            border-radius: 5px;
        }
        .skill-badge {
            display: inline-block;
            background: #e9ecef;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            margin: 2px;
        }
        .loading { text-align: center; padding: 40px; }
        .spinner {
            border: 3px solid #f3f3f3;
            border-top: 3px solid #667eea;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .job-reqs {
            background: #e7f3ff;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
        }
        .req-tag {
            display: inline-block;
            background: #667eea;
            color: white;
            padding: 3px 10px;
            border-radius: 15px;
            font-size: 12px;
            margin: 3px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📄 AI Resume Shortlister</h1>
        <div class="subtitle">Upload Job Description + Resumes → Get Detailed Rejection Reasons & Recommendations</div>
        
        <div class="section">
            <div class="section-title">📋 Job Description</div>
            <textarea id="jobDescription" rows="6" placeholder="Example: Looking for Software Engineer with Bachelor's degree in CS, 3+ years of experience in Python, SQL, and AWS..."></textarea>
        </div>
        
        <div class="section">
            <div class="section-title">📎 Upload Resumes (PDF, DOCX, or TXT)</div>
            <div class="upload-area" id="uploadArea">
                📂 Click or Drag & Drop files here
                <input type="file" id="fileInput" multiple accept=".pdf,.docx,.txt" style="display: none;">
            </div>
            <div class="file-list" id="fileList"></div>
        </div>
        
        <button id="shortlistBtn" onclick="shortlist()">🚀 Shortlist Candidates</button>
        
        <div id="results" style="margin-top: 30px;"></div>
    </div>

    <script>
        let selectedFiles = [];
        
        const uploadArea = document.getElementById('uploadArea');
        const fileInput = document.getElementById('fileInput');
        
        uploadArea.onclick = () => fileInput.click();
        uploadArea.ondragover = (e) => { e.preventDefault(); uploadArea.style.background = '#e8ebff'; };
        uploadArea.ondragleave = () => { uploadArea.style.background = '#f8f9ff'; };
        uploadArea.ondrop = (e) => {
            e.preventDefault();
            uploadArea.style.background = '#f8f9ff';
            addFiles(Array.from(e.dataTransfer.files));
        };
        
        fileInput.onchange = (e) => addFiles(Array.from(e.target.files));
        
        function addFiles(files) {
            const validFiles = files.filter(f => f.name.match(/\\.(pdf|docx|txt)$/i));
            selectedFiles.push(...validFiles);
            updateFileList();
        }
        
        function updateFileList() {
            const fileListDiv = document.getElementById('fileList');
            fileListDiv.innerHTML = selectedFiles.map((file, idx) => 
                `<div class="file-tag">📄 ${file.name} <span class="remove-file" onclick="removeFile(${idx})">×</span></div>`
            ).join('');
        }
        
        function removeFile(index) {
            selectedFiles.splice(index, 1);
            updateFileList();
        }
        
        async function shortlist() {
            const jobDescription = document.getElementById('jobDescription').value.trim();
            
            if (!jobDescription) {
                alert('Please enter job description');
                return;
            }
            
            if (selectedFiles.length === 0) {
                alert('Please upload at least one resume');
                return;
            }
            
            const btn = document.getElementById('shortlistBtn');
            btn.disabled = true;
            btn.innerHTML = '⏳ Processing...';
            
            const resultsDiv = document.getElementById('results');
            resultsDiv.innerHTML = '<div class="loading"><div class="spinner"></div><p>Analyzing resumes...</p></div>';
            
            const formData = new FormData();
            formData.append('job_description', jobDescription);
            selectedFiles.forEach(file => formData.append('resumes', file));
            
            try {
                const response = await fetch('/upload', { method: 'POST', body: formData });
                const data = await response.json();
                
                if (data.success) {
                    displayResults(data);
                } else {
                    resultsDiv.innerHTML = `<div style="color: red; padding: 20px; text-align: center;">Error: ${data.error}</div>`;
                }
            } catch (error) {
                resultsDiv.innerHTML = `<div style="color: red; padding: 20px; text-align: center;">Error: ${error.message}</div>`;
            } finally {
                btn.disabled = false;
                btn.innerHTML = '🚀 Shortlist Candidates';
            }
        }
        
        function displayResults(data) {
            // Show job requirements summary
            let html = '<div class="job-reqs"><strong>📋 Job Requirements Summary:</strong><br>';
            if (data.job_requirements.required_degree.length) {
                html += `<span class="req-tag">🎓 ${data.job_requirements.required_degree.join(', ')}</span>`;
            }
            if (data.job_requirements.min_experience > 0) {
                html += `<span class="req-tag">💼 ${data.job_requirements.min_experience}+ years experience</span>`;
            }
            data.job_requirements.required_skills.slice(0, 10).forEach(skill => {
                html += `<span class="req-tag">🔧 ${skill}</span>`;
            });
            html += '</div>';
            
            // Stats
            html += '<div class="stats">';
            html += `<div class="stat-card"><div class="stat-number">${data.stats.total}</div><div>Total</div></div>`;
            html += `<div class="stat-card"><div class="stat-number">${data.stats.qualified}</div><div>✅ Qualified</div></div>`;
            html += `<div class="stat-card"><div class="stat-number">${data.stats.not_qualified}</div><div>❌ Not Qualified</div></div>`;
            html += `<div class="stat-card"><div class="stat-number">${Math.round(data.stats.avg_score)}</div><div>Avg Score</div></div>`;
            html += '</div>';
            
            // Results
            data.results.forEach((result, idx) => {
                const isQualified = result.qualified;
                html += `
                    <div class="result-card ${isQualified ? 'qualified' : 'not-qualified'}" onclick="toggleDetails(${idx})">
                        <div class="result-header">
                            <div>
                                <strong>📄 ${result.filename}</strong><br>
                                <span style="padding: 4px 12px; border-radius: 20px; font-size: 12px; background: ${isQualified ? '#28a745' : '#dc3545'}; color: white;">
                                    ${isQualified ? '✅ QUALIFIED' : '❌ NOT QUALIFIED'}
                                </span>
                            </div>
                            <div class="score">Score: ${result.score}/100</div>
                        </div>
                        ${!isQualified && result.rejection_reason ? `
                            <div class="rejection-box" style="margin-top: 10px;">
                                <strong>⚠️ Rejection Reason:</strong> ${result.rejection_reason}
                            </div>
                        ` : ''}
                        <div id="details_${idx}" class="details-content">
                            ${result.matched && result.matched.length > 0 ? `
                                <div class="matched-list">
                                    <strong>✅ Matched Requirements:</strong><br>
                                    ${result.matched.join('<br>')}
                                </div>
                            ` : ''}
                            ${result.missing && result.missing.length > 0 ? `
                                <div class="missing-list">
                                    <strong>❌ Missing Requirements:</strong><br>
                                    ${result.missing.join('<br>')}
                                </div>
                            ` : ''}
                            ${result.details && result.details.found_skills && result.details.found_skills.length > 0 ? `
                                <div style="margin-top: 10px;">
                                    <strong>🔧 Skills Found:</strong><br>
                                    ${result.details.found_skills.map(s => `<span class="skill-badge">${s}</span>`).join('')}
                                </div>
                            ` : ''}
                            ${result.recommendation && result.recommendation.length > 0 ? `
                                <div class="recommendation-box">
                                    <strong>💡 Recommendations to Improve:</strong><br>
                                    ${result.recommendation.map(r => `• ${r}`).join('<br>')}
                                </div>
                            ` : ''}
                            ${result.details && result.details.found_experience > 0 ? `
                                <div style="margin-top: 10px; color: #666;">
                                    <strong>💼 Experience:</strong> ${result.details.found_experience} years
                                </div>
                            ` : ''}
                        </div>
                    </div>
                `;
            });
            
            document.getElementById('results').innerHTML = html;
        }
        
        function toggleDetails(id) {
            const details = document.getElementById(`details_${id}`);
            details.classList.toggle('show');
        }
    </script>
</body>
</html>'''

# Write the HTML file
with open('index.html', 'w', encoding='utf-8') as f:
    f.write(HTML_CONTENT)

print("=" * 60)
print("🎯 Resume Shortlister with Detailed Rejection Reasons")
print("=" * 60)
print("\n✅ Setup complete!")
print("\n📁 Files created:")
print("   - index.html (frontend with rejection reasons)")
print("   - server.py (backend processor)")
print("\n🚀 To start the server, run:")
print("   python server.py")
print("\n📂 Then open your browser and go to:")
print("   http://localhost:8000")
print("\n" + "=" * 60)

# Start the server
PORT = 8080

with socketserver.TCPServer(("", PORT), ResumeHandler) as httpd:
    print(f"\n✨ Server running at http://localhost:{PORT}")
    print("📊 Features:")
    print("   - Detailed rejection reasons")
    print("   - Skill gap analysis")
    print("   - Improvement recommendations")
    print("   - PDF/DOCX/TXT support")
    print("\nPress Ctrl+C to stop the server\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped.")