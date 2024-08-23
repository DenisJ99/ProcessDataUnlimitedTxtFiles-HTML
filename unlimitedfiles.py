import re
from collections import defaultdict

def extract_data(text):
    # Initialize dictionaries to store process and thread data
    data = {}
    process_names = {}
    event_counts = {'THRECEIVE': {}, 'THCONDVAR': {}, 'THREPLY': {}, 'THSEM': {}, 'THMUTEX': {}, 'THNANOSLEEP': {}}
    cpu_events = {}
    thread_cpu_events = defaultdict(lambda: defaultdict(list))
    thread_kernel_counts = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))  # New dictionary to store kernel call counts
    thread_running_time = defaultdict(lambda: defaultdict(lambda: {'total': 0, 'msec': 0, 'cpu_usage': 0}))  # New dictionary to store running time

    # Variables to keep track of the current process and thread
    current_pid = current_tid = current_name = None
    last_running_thread = {}
    running_start_times = defaultdict(lambda: defaultdict(int))
    unique_cpus = set()

    # Process each line in the input text
    for line in text.split('\n'):
        # Match the process ID in the line
        pid_match = re.search(r'pid:(\d+)', line)
        if pid_match:
            current_pid = pid_match.group(1)
            if current_pid not in data:
                data[current_pid] = {}
            current_tid = current_name = None

        if current_pid:
            # Match the thread ID in the line
            tid_match = re.search(r'tid:(\d+)', line)
            if tid_match:
                current_tid = tid_match.group(1)
                if current_tid not in data[current_pid]:
                    data[current_pid][current_tid] = "Unnamed Thread"
                if current_pid not in thread_cpu_events:
                    thread_cpu_events[current_pid] = {}
                if current_tid not in thread_cpu_events[current_pid]:
                    thread_cpu_events[current_pid][current_tid] = []

            # Match the thread or process name in the line
            name_match = re.search(r'name:(.+)', line)
            if name_match:
                current_name = name_match.group(1).strip()
                if current_tid is None:
                    if current_pid not in process_names:
                        process_names[current_pid] = current_name
                else:
                    data[current_pid][current_tid] = current_name

            # Match and count specific events in the line
            counted_events = set()
            for event in event_counts:
                if event in line and current_tid and event not in counted_events:
                    event_counts[event].setdefault(current_pid, {}).setdefault(current_tid, 0)
                    event_counts[event][current_pid][current_tid] += 1
                    counted_events.add(event)

        # Match the CPU ID in the line
        cpu_match = re.search(r'CPU:(\d+)', line)
        if cpu_match:
            cpu_id = cpu_match.group(1)
            unique_cpus.add(cpu_id)
            thread_running_match = re.search(r'THREAD\s+:THRUNNING\s+pid:(\d+)\s+tid:(\d+)', line)
            if thread_running_match:
                pid = thread_running_match.group(1)
                tid = thread_running_match.group(2)
                last_running_thread[cpu_id] = (pid, tid)

        # Match and count kernel events in the line
        event_match = re.search(r'KER_(CALL)\s+:(\S+)', line)
        if cpu_match and event_match:
            cpu_id = cpu_match.group(1)
            event_name = event_match.group(2).split()[0]
            if cpu_id in last_running_thread:
                pid, tid = last_running_thread[cpu_id]
                thread_cpu_events[pid][tid].append((cpu_id, event_name))
                thread_kernel_counts[pid][tid][event_name] += 1  # Update kernel call count

            cpu_events.setdefault(event_name, {}).setdefault(cpu_id, 0)
            cpu_events[event_name][cpu_id] += 1

        # Calculate running time
        time_match = re.search(r't:(\d+)\.(\d+)\.(\d+)us', line)
        if time_match:
            timestamp = int(time_match.group(1)) * 1_000_000 + int(time_match.group(2)) * 1_000 + int(time_match.group(3))

            if thread_running_match:
                running_start_times[pid][tid] = timestamp
            else:
                thread_match = re.search(r'pid:(\d+)\s+tid:(\d+)', line)
                if thread_match:
                    pid = thread_match.group(1)
                    tid = thread_match.group(2)
                    if tid in running_start_times[pid]:
                        start_time = running_start_times[pid][tid]
                        running_time = timestamp - start_time
                        thread_running_time[pid][tid]['total'] += running_time
                        thread_running_time[pid][tid]['msec'] = thread_running_time[pid][tid]['total'] / 1_000
                        del running_start_times[pid][tid]

    # Calculate CPU usage
    num_cpus = len(unique_cpus) * 10  # Total number of unique CPUs
    for pid, threads in thread_running_time.items():
        for tid, times in threads.items():
            times['cpu_usage'] = times['msec'] / num_cpus if num_cpus else 0

    return data, process_names, event_counts, cpu_events, thread_cpu_events, thread_kernel_counts, thread_running_time

def write_to_html(extracted_data_list, output_file, file_names):
    total_cpu_events_list = []
    for extracted_data in extracted_data_list:
        total_cpu_events = defaultdict(lambda: defaultdict(int))
        data, process_names, event_counts, cpu_events, thread_cpu_events, thread_kernel_counts, thread_running_time = extracted_data
        for pid, threads in thread_cpu_events.items():
            for tid, events in threads.items():
                for cpu_id, event_name in events:
                    total_cpu_events[event_name][cpu_id] += 1
        total_cpu_events_list.append(total_cpu_events)

    with open(output_file, 'w', encoding='utf-8') as file:
        file.write("<html><head><title>Process Report</title>")
        file.write("<style>")
        file.write("""
            body { font-family: Arial, sans-serif; margin: 20px; }
            h1, h2, p { margin: 0 0 10px; }
            select { margin-right: 10px; }
            table { width: 100%; border-collapse: collapse; margin-top: 10px; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #f2f2f2; color: black; }
            tr:nth-child(even) { background-color: #f9f9f9; }
            tr:hover { background-color: #f1f1f1; }
            .totals-row { font-weight: bold; background-color: #e2e2e2; }
            button { margin-left: 5px; }
            .chart-container { display: flex; justify-content: space-around; margin-top: 20px; }
            .chart-container canvas { max-width: 50%; max-height: 100%; } /* Adjusted max-width to fit both charts */
            .toggle-button { position: fixed; top: 10px; right: 10px; padding: 10px 20px; background-color: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer; }
            .dark-mode { background-color: #1e1e1e; color: #ffffff; } /* Lighter dark mode background */
            .dark-mode th, .dark-mode td { border-color: #444444; color: #ffffff; }
            .dark-mode th { background-color: #333333; color: #ffffff; }
            .dark-mode tr:nth-child(even) { background-color: #2a2a2a; }
            .dark-mode tr:hover { background-color: #333333; }
            .dark-mode .totals-row { background-color: #444444; color: #ffffff; }
            .dark-mode select, .dark-mode button { background-color: #444444; color: #ffffff; }
        """)
        file.write("</style>")
        file.write('<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>')
        file.write("<script>")
        file.write("""
            var currentSort = {};
            var charts = {};

            function toggleDarkMode() {
                document.body.classList.toggle('dark-mode');
                updateTableHeaderColors();
                updateChartColors();
            }

            function updateTableHeaderColors() {
                var textColor = document.body.classList.contains('dark-mode') ? 'white' : 'black';
                var thElements = document.getElementsByTagName('th');
                for (var i = 0; i < thElements.length; i++) {
                    thElements[i].style.color = textColor;
                }
            }

            function updateChartColors() {
                var textColor = document.body.classList.contains('dark-mode') ? 'white' : 'black';
                var gridColor = document.body.classList.contains('dark-mode') ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)';
                for (var chartId in charts) {
                    if (charts.hasOwnProperty(chartId)) {
                        charts[chartId].options.scales.x.ticks.color = textColor;
                        charts[chartId].options.scales.y.ticks.color = textColor;
                        charts[chartId].options.scales.x.grid.color = gridColor;
                        charts[chartId].options.scales.y.grid.color = gridColor;
                        charts[chartId].options.plugins.legend.labels.color = textColor;
                        charts[chartId].update();
                    }
                }
            }

            function selectFile() {
                var selectedFile = document.getElementById('fileSelect').value;
                var fileContainers = document.getElementsByClassName('file-container');
                for (var i = 0; i < fileContainers.length; i++) {
                    fileContainers[i].style.display = (fileContainers[i].id === selectedFile) ? 'block' : 'none';
                }
            }

            function filterByProcess(fileNumber) {
                var processSelect = document.getElementById('processSelect' + fileNumber);
                var selectedProcess = processSelect.options[processSelect.selectedIndex].value;
                var processName = processSelect.options[processSelect.selectedIndex].text;
                var threadTable = document.getElementById('threadTable' + fileNumber);
                var threadRows = threadTable.getElementsByTagName('tr');
                var threadSelect = document.getElementById('threadNameSelect' + fileNumber);
                var allProcessesSummary = document.getElementById('allProcessesSummary' + fileNumber);
                var kernelTable = document.getElementById('kernelTable' + fileNumber); // New kernel call table
                var kernelRows = kernelTable.getElementsByTagName('tr');
                var runningTimeTable = document.getElementById('runningTimeTable' + fileNumber); // New running time table
                var runningTimeRows = runningTimeTable.getElementsByTagName('tr');
                var viewSelect = document.getElementById('viewSelect' + fileNumber);
                var viewOptions = ['all', 'threadTable'];

                var nameField = document.getElementById('processName' + fileNumber);
                var pidField = document.getElementById('processID' + fileNumber);
                nameField.textContent = processName.split(' (PID: ')[0].split('/').pop();
                pidField.textContent = selectedProcess;

                threadSelect.innerHTML = '<option value="all">All Threads</option>';

                var totals = { 'THRECEIVE': 0, 'THCONDVAR': 0, 'THREPLY': 0, 'THSEM': 0, 'THMUTEX': 0, 'THNANOSLEEP': 0 };

                for (var i = 1; i < threadRows.length - 1; i++) {
                    var processId = threadRows[i].getAttribute('data-pid');
                    var threadName = threadRows[i].getElementsByTagName('td')[0].innerText;
                    if (selectedProcess === 'all' || processId === selectedProcess) {
                        threadRows[i].style.display = '';
                        totals.THRECEIVE += parseInt(threadRows[i].getElementsByTagName('td')[2].innerText);
                        totals.THCONDVAR += parseInt(threadRows[i].getElementsByTagName('td')[3].innerText);
                        totals.THREPLY += parseInt(threadRows[i].getElementsByTagName('td')[4].innerText);
                        totals.THSEM += parseInt(threadRows[i].getElementsByTagName('td')[5].innerText);
                        totals.THMUTEX += parseInt(threadRows[i].getElementsByTagName('td')[6].innerText);
                        totals.THNANOSLEEP += parseInt(threadRows[i].getElementsByTagName('td')[7].innerText);

                        if (selectedProcess !== 'all') {
                            var option = document.createElement('option');
                            option.value = threadName;
                            option.text = threadName;
                            threadSelect.add(option);
                        }
                    } else {
                        threadRows[i].style.display = 'none';
                    }
                }

                document.getElementById('total-threceive' + fileNumber).innerText = totals.THRECEIVE;
                document.getElementById('total-thcondvar' + fileNumber).innerText = totals.THCONDVAR;
                document.getElementById('total-threply' + fileNumber).innerText = totals.THREPLY;
                document.getElementById('total-thsem' + fileNumber).innerText = totals.THSEM;
                document.getElementById('total-thmutex' + fileNumber).innerText = totals.THMUTEX;
                document.getElementById('total-thnanosleep' + fileNumber).innerText = totals.THNANOSLEEP;

                updateLineChart(totals, fileNumber);
                updateBarChart(totals, fileNumber);

                if (selectedProcess === 'all') {
                    allProcessesSummary.style.display = 'table';
                    threadTable.style.display = 'table';  // Show thread table for all processes
                    kernelTable.style.display = 'none';  // Hide the kernel table when all processes are selected
                    runningTimeTable.style.display = 'none';  // Hide the running time table when all processes are selected
                    viewOptions = ['all', 'threadTable', 'kernelTable'];
                } else {
                    allProcessesSummary.style.display = 'none';
                    threadTable.style.display = 'table';
                    kernelTable.style.display = 'table';  // Show the kernel table when a specific process is selected
                    runningTimeTable.style.display = 'table';  // Show the running time table when a specific process is selected

                    // Sort kernel headers based on total counts for the selected process
                    var kernelHeaders = Array.from(kernelTable.rows[0].cells).slice(2).map(cell => cell.textContent);
                    var kernelCounts = {};
                    for (var i = 1; i < kernelRows.length; i++) {
                        var row = kernelRows[i];
                        if (row.getAttribute('data-pid') === selectedProcess) {
                            for (var j = 2; j < row.cells.length; j++) {
                                var header = kernelHeaders[j - 2];
                                var count = parseInt(row.cells[j].textContent);
                                if (!isNaN(count)) {
                                    kernelCounts[header] = (kernelCounts[header] || 0) + count;
                                }
                            }
                        }
                    }
                    var sortedKernelHeaders = Object.keys(kernelCounts).sort((a, b) => kernelCounts[b] - kernelCounts[a]);

                    // Filter out columns with all zero values
                    sortedKernelHeaders = sortedKernelHeaders.filter(header => kernelCounts[header] > 0);

                    // Update kernel table header
                    kernelTable.rows[0].innerHTML = "<th>Thread Name</th><th>Thread ID</th>" + sortedKernelHeaders.map(header => `<th>${header}</th>`).join("");

                    // Update kernel table rows
                    for (var i = 1; i < kernelRows.length; i++) {
                        var row = kernelRows[i];
                        if (row.getAttribute('data-pid') === selectedProcess) {
                            var cells = Array.from(row.cells).slice(2);
                            row.innerHTML = "<td>" + row.cells[0].innerHTML + "</td><td>" + row.cells[1].innerHTML + "</td>" + sortedKernelHeaders.map(header => {
                                var cell = cells.find(cell => cell.getAttribute('data-header') === header);
                                return cell ? `<td data-header="${header}">${cell.textContent}</td>` : "<td>0</td>";
                            }).join("");
                        }
                    }

                    // Update running time table rows
                    for (var i = 1; i < runningTimeRows.length; i++) {
                        var row = runningTimeRows[i];
                        if (row.getAttribute('data-pid') === selectedProcess) {
                            row.style.display = '';
                        } else {
                            row.style.display = 'none';
                        }
                    }

                    // Dynamically update view options based on available data for the selected process
                    viewOptions = ['all', 'threadTable'];
                    var hasCPUData = Array.from(kernelRows).some(row => row.style.display === '');
                    var hasRunningTimeData = Array.from(runningTimeRows).some(row => row.style.display === '');
                    if (hasCPUData) viewOptions.push('kernelTable');
                    if (hasRunningTimeData) viewOptions.push('runningTimeTable');
                }

                // Update view select options
                viewSelect.innerHTML = '';
                viewOptions.forEach(function(option) {
                    var text = option === 'threadTable' ? 'Threads' : option === 'kernelTable' ? 'CPU' : option === 'runningTimeTable' ? 'Running Time' : 'All';
                    var opt = document.createElement('option');
                    opt.value = option;
                    opt.textContent = text;
                    viewSelect.appendChild(opt);
                });

                filterByThreadName(fileNumber);
            }

            function filterByThreadName(fileNumber) {
                var threadSelect = document.getElementById('threadNameSelect' + fileNumber);
                var selectedThreadName = threadSelect.options[threadSelect.selectedIndex].value;
                var table = document.getElementById('threadTable' + fileNumber);
                var tr = table.getElementsByTagName('tr');
                var processSelect = document.getElementById('processSelect' + fileNumber);
                var selectedProcess = processSelect.options[processSelect.selectedIndex].value;
                var kernelTable = document.getElementById('kernelTable' + fileNumber); // New kernel call table
                var kernelRows = kernelTable.getElementsByTagName('tr');
                var runningTimeTable = document.getElementById('runningTimeTable' + fileNumber); // New running time table
                var runningTimeRows = runningTimeTable.getElementsByTagName('tr');
                var totals = { 'THRECEIVE': 0, 'THCONDVAR': 0, 'THREPLY': 0, 'THSEM': 0, 'THMUTEX': 0, 'THNANOSLEEP': 0 };
                var threadCounts = { 'THRECEIVE': [], 'THCONDVAR': [], 'THREPLY': [], 'THSEM': [], 'THMUTEX': [], 'THNANOSLEEP': [] };

                for (var i = 1; i < tr.length - 1; i++) {
                    var td = tr[i].getElementsByTagName('td')[0];
                    var processId = tr[i].getAttribute('data-pid');
                    var threadName = td.textContent || td.innerText;

                    if (selectedProcess === 'all' || processId === selectedProcess) {
                        if (selectedThreadName === 'all' || threadName === selectedThreadName) {
                            tr[i].style.display = '';
                            var threadId = tr[i].getElementsByTagName('td')[1].innerText;
                            threadCounts.THRECEIVE.push({threadName: threadName, count: parseInt(tr[i].getElementsByTagName('td')[2].innerText)});
                            threadCounts.THCONDVAR.push({threadName: threadName, count: parseInt(tr[i].getElementsByTagName('td')[3].innerText)});
                            threadCounts.THREPLY.push({threadName: threadName, count: parseInt(tr[i].getElementsByTagName('td')[4].innerText)});
                            threadCounts.THSEM.push({threadName: threadName, count: parseInt(tr[i].getElementsByTagName('td')[5].innerText)});
                            threadCounts.THMUTEX.push({threadName: threadName, count: parseInt(tr[i].getElementsByTagName('td')[6].innerText)});
                            threadCounts.THNANOSLEEP.push({threadName: threadName, count: parseInt(tr[i].getElementsByTagName('td')[7].innerText)});
                        } else {
                            tr[i].style.display = 'none';
                        }
                    }
                }

                // Sort kernel rows based on the selected thread's counts
                for (var i = 1; i < kernelRows.length; i++) {
                    var processId = kernelRows[i].getAttribute('data-pid');
                    var threadName = kernelRows[i].getElementsByTagName('td')[0].innerText;
                    if (selectedProcess === 'all' || (processId === selectedProcess && (selectedThreadName === 'all' || threadName === selectedThreadName))) {
                        if (selectedThreadName !== 'all') {
                            var cells = Array.from(kernelRows[i].cells).slice(2);
                            var kernelCounts = {};
                            cells.forEach(cell => {
                                var count = parseInt(cell.textContent);
                                if (!isNaN(count)) {
                                    kernelCounts[cell.getAttribute('data-header')] = count;
                                }
                            });
                            var sortedKernelHeaders = Object.keys(kernelCounts).sort((a, b) => kernelCounts[b] - kernelCounts[a]);

                            // Filter out columns with all zero values
                            sortedKernelHeaders = sortedKernelHeaders.filter(header => kernelCounts[header] > 0);

                            // Update kernel table header
                            kernelTable.rows[0].innerHTML = "<th>Thread Name</th><th>Thread ID</th>" + sortedKernelHeaders.map(header => `<th>${header}</th>`).join("");
                            kernelRows[i].innerHTML = "<td>" + kernelRows[i].cells[0].innerHTML + "</td><td>" + kernelRows[i].cells[1].innerHTML + "</td>" + sortedKernelHeaders.map(header => {
                                var cell = cells.find(cell => cell.getAttribute('data-header') === header);
                                return cell ? `<td data-header="${header}">${cell.textContent}</td>` : "<td>0</td>";
                            }).join("");
                        }
                        kernelRows[i].style.display = '';
                    } else {
                        kernelRows[i].style.display = 'none';
                    }
                }

                // Filter running time rows based on selected thread name
                for (var i = 1; i < runningTimeRows.length; i++) {
                    var td = runningTimeRows[i].getElementsByTagName('td')[0];
                    var processId = runningTimeRows[i].getAttribute('data-pid');
                    var threadName = td.textContent || td.innerText;

                    if (selectedProcess === 'all' || processId === selectedProcess) {
                        if (selectedThreadName === 'all' || threadName === selectedThreadName) {
                            runningTimeRows[i].style.display = '';
                        } else {
                            runningTimeRows[i].style.display = 'none';
                        }
                    }
                }
            }

            function sortTable(header, direction, fileNumber) {
                var table = document.getElementById('threadTable' + fileNumber);
                var rows = Array.from(table.rows).slice(1, -1); // exclude header and totals row
                var index = Array.from(table.rows[0].cells).findIndex(cell => cell.textContent.includes(header));
                rows.sort((a, b) => {
                    var aVal = parseInt(a.cells[index].innerText);
                    var bVal = parseInt(b.cells[index].innerText);
                    return direction === 'asc' ? aVal - bVal : bVal - aVal;
                });
                rows.forEach(row => table.tBodies[0].insertBefore(row, table.tBodies[0].lastElementChild));
            }

            function sortRunningTimeTable(header, direction, fileNumber) {
                var table = document.getElementById('runningTimeTable' + fileNumber);
                var rows = Array.from(table.rows).slice(1); // exclude header
                var index = Array.from(table.rows[0].cells).findIndex(cell => cell.textContent.includes(header));
                rows.sort((a, b) => {
                    var aVal = header === 'Thread ID' ? parseInt(a.cells[index].innerText) : parseFloat(a.cells[index].innerText);
                    var bVal = header === 'Thread ID' ? parseInt(b.cells[index].innerText) : parseFloat(b.cells[index].innerText);
                    return direction === 'asc' ? aVal - bVal : bVal - aVal;
                });
                rows.forEach(row => table.tBodies[0].appendChild(row));
            }

            function showTable(tableId, fileNumber) {
                var allTables = ['threadTable', 'kernelTable', 'runningTimeTable', 'allProcessesSummary'];
                allTables.forEach(function(id) {
                    document.getElementById(id + fileNumber).style.display = 'none';
                });

                if (tableId === 'all') {
                    document.getElementById('threadTable' + fileNumber).style.display = 'table';
                    if (document.getElementById('processSelect' + fileNumber).value === 'all') {
                        document.getElementById('allProcessesSummary' + fileNumber).style.display = 'table';
                    } else {
                        document.getElementById('kernelTable' + fileNumber).style.display = 'table';
                        document.getElementById('runningTimeTable' + fileNumber).style.display = 'table';
                    }
                } else if (tableId === 'kernelTable' && document.getElementById('processSelect' + fileNumber).value === 'all') {
                    document.getElementById('allProcessesSummary' + fileNumber).style.display = 'table';
                } else {
                    document.getElementById(tableId + fileNumber).style.display = 'table';
                }
            }

            function updateLineChart(totals, fileNumber) {
                var ctx = document.getElementById('line-chart' + fileNumber).getContext('2d');
                var data = [totals.THRECEIVE, totals.THCONDVAR, totals.THREPLY, totals.THSEM, totals.THMUTEX, totals.THNANOSLEEP];
                var labels = ['THRECEIVE', 'THCONDVAR', 'THREPLY', 'THSEM', 'THMUTEX', 'THNANOSLEEP'];
                if (charts['line' + fileNumber]) {
                    charts['line' + fileNumber].destroy();
                }
                charts['line' + fileNumber] = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: 'Total Counts',
                            data: data,
                            backgroundColor: 'rgba(54, 162, 235, 0.2)',
                            borderColor: 'rgba(54, 162, 235, 1)',
                            borderWidth: 1,
                            fill: true
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                beginAtZero: true,
                                ticks: {
                                    color: document.body.classList.contains('dark-mode') ? 'white' : 'black'
                                },
                                grid: {
                                    color: document.body.classList.contains('dark-mode') ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)'
                                }
                            },
                            x: {
                                ticks: {
                                    color: document.body.classList.contains('dark-mode') ? 'white' : 'black'
                                },
                                grid: {
                                    color: document.body.classList.contains('dark-mode') ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)'
                                }
                            }
                        },
                        plugins: {
                            legend: {
                                labels: {
                                    color: document.body.classList.contains('dark-mode') ? 'white' : 'black'
                                }
                            }
                        }
                    }
                });
            }

            function updateBarChart(totals, fileNumber) {
                var ctx = document.getElementById('bar-chart' + fileNumber).getContext('2d');
                var data = [totals.THRECEIVE, totals.THCONDVAR, totals.THREPLY, totals.THSEM, totals.THMUTEX, totals.THNANOSLEEP];
                var labels = ['THRECEIVE', 'THCONDVAR', 'THREPLY', 'THSEM', 'THMUTEX', 'THNANOSLEEP'];
                if (charts['bar' + fileNumber]) {
                    charts['bar' + fileNumber].destroy();
                }
                charts['bar' + fileNumber] = new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: 'Total Counts',
                            data: data,
                            backgroundColor: 'rgba(54, 162, 235, 0.2)',
                            borderColor: 'rgba(54, 162, 235, 1)',
                            borderWidth: 1
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                beginAtZero: true,
                                ticks: {
                                    color: document.body.classList.contains('dark-mode') ? 'white' : 'black'
                                },
                                grid: {
                                    color: document.body.classList.contains('dark-mode') ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)'
                                }
                            },
                            x: {
                                ticks: {
                                    color: document.body.classList.contains('dark-mode') ? 'white' : 'black'
                                },
                                grid: {
                                    color: document.body.classList.contains('dark-mode') ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)'
                                }
                            }
                        },
                        plugins: {
                            legend: {
                                labels: {
                                    color: document.body.classList.contains('dark-mode') ? 'white' : 'black'
                                }
                            }
                        }
                    }
                });
            }

            document.addEventListener('DOMContentLoaded', function() {
                var fileCount = document.getElementById('fileCount').value;
                for (var i = 1; i <= fileCount; i++) {
                    filterByProcess(i);
                    var viewSelect = document.getElementById('viewSelect' + i);
                    viewSelect.addEventListener('change', function() {
                        showTable(this.value, i);
                    });
                }
                selectFile();
                document.getElementById('fileSelect').addEventListener('change', selectFile);
            });
        """)
        file.write("</script></head><body>")
        file.write(f"<h1>Process Data</h1>")
        file.write("<button class='toggle-button' onclick='toggleDarkMode()'>Toggle Dark Mode</button>")
        file.write("Select file: <select id='fileSelect'>")
        for i, file_name in enumerate(file_names):
            file.write(f"<option value='file{i+1}'>{file_name}</option>")
        file.write("</select>")
        file.write(f"<input type='hidden' id='fileCount' value='{len(file_names)}'>")
        for i, (data, process_names, event_counts, cpu_events, thread_cpu_events, thread_kernel_counts, thread_running_time) in enumerate(extracted_data_list):
            file_number = i + 1
            file.write(f"<div id='file{file_number}' class='file-container' style='display:none;'><h2>{file_names[i]}</h2>")
            file.write(f"View: <select id='viewSelect{file_number}' onchange='showTable(this.value, {file_number})'>")
            file.write("<option value='all'>All</option>")
            file.write("<option value='threadTable'>Threads</option>")
            file.write("<option value='kernelTable'>CPU</option>")
            file.write("<option value='runningTimeTable'>Running Time</option>")
            file.write("</select>")
            file.write(f"Select a process: <select id='processSelect{file_number}' onchange='filterByProcess({file_number})'>")
            file.write("<option value='all'>All Processes</option>")
            for pid, pname in process_names.items():
                pname_display = pname.split('/')[-1].capitalize()  # Extract the name after the last "/" and capitalize it
                file.write(f"<option value='{pid}'>{pname_display} (PID: {pid})</option>")
            file.write("</select>")
            file.write(f" Select a thread name: <select id='threadNameSelect{file_number}' onchange='filterByThreadName({file_number})'>")
            file.write("<option value='all'>All Threads</option>")
            file.write("</select>")
            file.write(f"<p>Name: <span id='processName{file_number}'></span></p>")
            file.write(f"<p>PID: <span id='processID{file_number}'></span></p>")
            file.write(f'<div class="chart-container"><canvas id="line-chart{file_number}"></canvas><canvas id="bar-chart{file_number}"></canvas></div>')
            file.write(f"<table id='threadTable{file_number}'><tr>")
            headers = ["Thread Name", "Thread ID", "THRECEIVE", "THCONDVAR", "THREPLY", "THSEM", "THMUTEX", "THNANOSLEEP"]
            file.write("<th>Thread Name</th>")  # No sorting buttons for "Thread Name"
            for header in headers[1:]:
                file.write(f"<th>{header} <button onclick=\"sortTable('{header}', 'asc', {file_number})\">&#9650;</button><button onclick=\"sortTable('{header}', 'desc', {file_number})\">&#9660;</button></th>")
            file.write("</tr>")

            for pid, threads in data.items():
                for tid, name in threads.items():
                    file.write(f"<tr data-pid='{pid}'>")
                    file.write(f"<td>{name}</td>")
                    file.write(f"<td>{tid}</td>")
                    for event in headers[2:]:
                        file.write(f"<td>{event_counts[event].get(pid, {}).get(tid, 0)}</td>")
                    file.write("</tr>")
            
            file.write(f"<tr class='totals-row'><td colspan='2'><strong>Totals</strong></td>")
            for event in headers[2:]:
                file.write(f"<td id='total-{event.lower()}{file_number}'></td>")
            file.write("</tr>")
            file.write("</table>")

            # Adding the new kernel call count table
            file.write(f"<table id='kernelTable{file_number}' style='display: none;'><tr>")
            kernel_headers = ["Thread Name", "Thread ID"] + sorted(set(k for pid in thread_kernel_counts for tid in thread_kernel_counts[pid] for k in thread_kernel_counts[pid][tid] if thread_kernel_counts[pid][tid][k] > 0))
            for header in kernel_headers:
                file.write(f"<th>{header}</th>")
            file.write("</tr>")
            for pid, threads in thread_kernel_counts.items():
                for tid in sorted(threads.keys(), key=lambda x: int(x)):
                    file.write(f"<tr data-pid='{pid}'>")
                    file.write(f"<td>{data[pid][tid]}</td>")
                    file.write(f"<td>{tid}</td>")
                    for header in kernel_headers[2:]:
                        file.write(f"<td data-header='{header}'>{threads[tid].get(header, 0)}</td>")
                    file.write("</tr>")
            file.write("</table>")

            # Adding the new running time table
            file.write(f"<table id='runningTimeTable{file_number}' style='display: none;'><tr>")
            running_time_headers = ["Thread Name", "Thread ID", "Running Time", "Running Time (MSEC)", "CPU Usage"]
            for header in running_time_headers:
                if header in ["Thread ID", "Running Time", "Running Time (MSEC)", "CPU Usage"]:
                    file.write(f"<th>{header} <button onclick=\"sortRunningTimeTable('{header}', 'asc', {file_number})\">&#9650;</button><button onclick=\"sortRunningTimeTable('{header}', 'desc', {file_number})\">&#9660;</button></th>")
                else:
                    file.write(f"<th>{header}</th>")
            file.write("</tr>")
            for pid, threads in thread_running_time.items():
                for tid, times in threads.items():
                    file.write(f"<tr data-pid='{pid}'>")
                    file.write(f"<td>{data[pid][tid]}</td>")
                    file.write(f"<td>{tid}</td>")
                    file.write(f"<td>{times['total']}</td>")
                    file.write(f"<td>{times['msec']}</td>")
                    file.write(f"<td>{times['cpu_usage']}</td>")
                    file.write("</tr>")
            file.write("</table>")

            # Summary table for all processes
            file.write(f"<div id='allProcessesSummary{file_number}' style='display: none;'>")
            file.write("<h2>Summary of CPU Events for All Processes</h2>")
            file.write("<table><tr><th>Event Name</th>")
            cpu_headers = sorted(set(cpu_id for events in total_cpu_events_list[i].values() for cpu_id in events))
            for cpu_id in cpu_headers:
                file.write(f"<th>CPU:{cpu_id}</th>")
            file.write("<th>Total</th></tr>")
            for event_name, cpus in total_cpu_events_list[i].items():
                file.write(f"<tr><td>{event_name}</td>")
                event_total = 0
                for cpu_id in cpu_headers:
                    count = cpus.get(cpu_id, 0)
                    file.write(f"<td>{count}</td>")
                    event_total += count
                file.write(f"<td>{event_total}</td></tr>")
            file.write("</table>")
            file.write("</div></div>")
        file.write("</body></html>")

def main():
    # Get the input and output file names from the user
    input_files = []
    while True:
        input_file = input("Please enter the name of an input text file (or 'done' to finish): ")
        if input_file.lower() == 'done':
            break
        input_files.append(input_file)
    output_file = input("Please enter the name of the output HTML file: ")

    # Read the input file content
    texts = []
    for input_file in input_files:
        with open(input_file, 'r') as file:
            texts.append(file.read())

    # Extract the data from the text
    extracted_data_list = [extract_data(text) for text in texts]
    
    # Write the extracted data to the output HTML file
    write_to_html(extracted_data_list, output_file, input_files)
    print(f"Data has been written to {output_file}.")

if __name__ == "__main__":
    main()
