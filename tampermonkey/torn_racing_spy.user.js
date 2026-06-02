// ==UserScript==
// @name         Torn Racing Spy
// @namespace    https://github.com/live-commentary-agent
// @version      0.5
// @description  Live race map view + leaderboard overlay for Torn City Racing
// @author       live-commentary-agent
// @match        https://www.torn.com/*
// @grant        GM_xmlhttpRequest
// @grant        unsafeWindow
// @connect      localhost
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    const SERVER  = 'http://localhost:8766/data';
    const MAX_LOG = 60;

    // -----------------------------------------------------------------------
    // Driver colours — assigned by leaderboard position index
    // -----------------------------------------------------------------------
    const COLORS = ['#ff4444','#44aaff','#44ff88','#ffaa00','#ff44ff','#44ffff'];

    // -----------------------------------------------------------------------
    // Per-track SVG paths auto-traced from Torn's track images (260×170 viewbox).
    // Key = image code extracted from img.img-track URL (e.g. "A5" from "A5.jpg").
    // -----------------------------------------------------------------------
    const MAP_W = 260, MAP_H = 170;
    const FALLBACK_PATH = 'M 130,155 C 200,155 240,135 240,100 C 240,55 200,15 130,15 C 60,15 20,55 20,100 C 20,135 60,155 130,155 Z';
    const TRACK_PATHS = {
        'A1':'M 58.5,72.2 L 61.5,66.6 L 71.5,58.3 L 76.0,40.2 L 80.5,31.9 L 86.5,32.6 L 106.5,45.1 L 115.5,52.7 L 123.0,61.1 L 125.5,62.4 L 128.0,65.2 L 129.5,65.9 L 132.0,67.3 L 132.5,68.0 L 134.0,68.7 L 134.5,68.7 L 136.5,70.1 L 137.0,70.1 L 139.0,71.5 L 141.5,71.5 L 145.5,70.1 L 149.0,73.6 L 177.5,71.5 L 203.0,79.1 L 202.0,80.5 L 195.0,93.7 L 188.5,102.7 L 179.5,109.6 L 168.0,111.0 L 164.0,124.2 L 161.5,128.4 L 154.5,130.4 L 144.5,120.7 L 139.0,117.3 L 135.0,114.5 L 133.0,117.3 L 129.5,118.0 L 126.5,114.5 L 123.5,115.9 L 118.5,111.0 L 114.0,112.4 L 114.0,108.9 L 109.0,104.8 L 104.0,102.0 L 98.5,103.4 L 88.0,97.1 L 82.5,93.0 L 64.5,81.2 Z',
        'A2':'M 73.5,77.0 L 72.0,70.8 L 70.5,61.1 L 72.5,52.7 L 83.5,40.2 L 86.5,35.4 L 89.0,20.8 L 96.0,10.4 L 96.0,9.7 L 104.5,7.6 L 114.0,6.9 L 122.0,8.3 L 127.0,9.0 L 136.0,13.9 L 142.5,19.4 L 144.0,27.8 L 151.0,34.7 L 151.0,42.3 L 156.5,45.1 L 161.5,54.8 L 164.5,61.1 L 168.5,68.7 L 169.0,69.4 L 175.0,81.9 L 178.5,93.7 L 183.5,100.6 L 181.5,109.6 L 175.5,113.1 L 172.0,128.4 L 163.0,148.5 L 161.5,154.0 L 157.0,159.6 L 150.0,161.7 L 140.0,156.1 L 133.0,154.7 L 120.5,156.8 L 112.5,159.6 L 112.0,159.6 L 103.5,150.6 L 102.5,142.9 L 97.0,135.3 L 95.0,125.6 L 92.0,118.0 L 88.0,107.6 L 85.5,103.4 L 81.5,93.7 L 79.5,87.4 Z',
        'A3':'M 87.5,78.4 L 98.5,74.2 L 111.0,73.6 L 112.0,68.7 L 116.5,70.1 L 118.0,66.6 L 118.0,65.9 L 120.0,64.5 L 123.5,65.2 L 124.5,63.8 L 126.5,62.4 L 127.0,61.8 L 130.0,61.1 L 132.0,59.7 L 135.0,56.2 L 155.5,13.9 L 163.5,11.8 L 166.0,13.9 L 168.0,27.1 L 174.5,43.0 L 175.0,43.7 L 180.5,60.4 L 185.5,63.1 L 188.0,79.8 L 193.0,91.6 L 197.0,105.5 L 196.5,108.2 L 187.0,119.3 L 178.5,120.7 L 171.5,127.0 L 163.5,131.8 L 152.5,138.1 L 152.0,138.8 L 145.0,136.7 L 139.0,137.4 L 130.5,138.8 L 127.0,142.2 L 122.0,139.5 L 113.0,132.5 L 104.0,138.8 L 93.5,145.7 L 79.0,149.2 L 73.5,144.3 L 72.5,136.0 L 66.5,117.3 L 64.0,108.2 L 59.5,97.1 L 66.5,90.9 Z',
        'A4':'M 83.5,77.0 L 82.0,68.0 L 82.0,59.0 L 81.0,48.6 L 80.5,35.4 L 82.0,22.9 L 82.5,7.6 L 84.5,6.9 L 95.5,7.6 L 104.5,7.6 L 113.0,8.3 L 120.5,10.4 L 128.0,16.0 L 133.5,23.6 L 139.0,35.4 L 140.5,40.9 L 143.0,47.2 L 145.0,53.4 L 146.5,58.3 L 148.0,63.8 L 149.0,67.3 L 151.5,73.6 L 153.5,79.1 L 155.0,83.3 L 158.0,90.2 L 163.5,97.1 L 168.5,108.2 L 174.0,117.3 L 167.5,123.5 L 160.0,127.7 L 149.0,123.5 L 151.0,141.6 L 148.0,154.0 L 143.0,163.1 L 142.0,162.4 L 128.5,129.8 L 124.5,126.3 L 123.0,124.2 L 116.5,122.8 L 111.0,124.2 L 108.0,122.1 L 104.0,120.0 L 103.0,117.3 L 98.5,108.9 L 99.5,103.4 L 96.5,99.9 L 96.5,92.3 L 88.5,85.3 Z',
        'A5':'M 61.0,74.2 L 61.0,72.9 L 64.5,61.1 L 81.0,19.4 L 83.5,14.6 L 90.0,13.2 L 104.5,25.7 L 114.5,32.6 L 120.5,38.2 L 126.0,42.3 L 130.0,45.8 L 134.0,48.6 L 137.0,50.7 L 141.0,53.4 L 144.5,56.2 L 147.5,59.0 L 152.0,62.4 L 155.5,65.2 L 160.0,68.7 L 165.0,72.9 L 172.5,78.4 L 182.5,84.7 L 195.5,92.3 L 196.0,111.0 L 197.5,122.1 L 197.5,139.5 L 196.0,155.4 L 194.0,158.9 L 169.0,140.9 L 155.5,144.3 L 152.0,146.4 L 144.0,147.1 L 140.5,143.6 L 134.5,139.5 L 128.5,140.2 L 125.0,133.9 L 121.0,129.1 L 115.0,124.2 L 111.0,125.6 L 108.5,118.7 L 103.5,114.5 L 99.5,111.0 L 93.5,109.6 L 88.0,106.9 L 79.5,95.8 L 68.5,86.7 Z',
        'A6':'M 116.5,84.0 L 112.0,79.8 L 79.0,58.3 L 72.0,39.6 L 71.5,35.4 L 78.0,29.1 L 92.0,16.0 L 92.5,16.7 L 101.0,13.9 L 111.5,20.1 L 121.5,36.8 L 129.5,45.8 L 131.5,47.9 L 135.0,55.5 L 137.0,59.0 L 139.0,65.9 L 139.5,66.6 L 140.5,70.8 L 142.5,73.6 L 144.0,74.9 L 147.0,76.3 L 151.0,77.7 L 151.5,80.5 L 155.0,86.0 L 158.5,90.9 L 165.0,98.5 L 183.0,115.9 L 190.0,133.2 L 187.0,144.3 L 185.0,152.7 L 179.5,159.6 L 147.5,116.6 L 139.5,108.2 L 136.5,105.5 L 134.0,103.4 L 132.5,102.7 L 130.0,102.0 L 128.0,102.0 L 127.5,102.0 L 125.5,99.9 L 125.0,99.2 L 124.5,97.8 L 123.0,95.8 L 122.0,93.7 L 120.0,93.0 L 119.5,91.6 L 119.5,89.5 L 118.0,86.7 Z',
        'A7':'M 73.5,75.6 L 71.0,64.5 L 68.0,50.7 L 64.5,34.7 L 64.5,30.5 L 74.0,26.4 L 83.0,21.5 L 95.5,13.2 L 99.0,13.2 L 109.5,16.0 L 117.0,16.7 L 123.0,19.4 L 131.0,22.9 L 140.0,25.0 L 150.0,13.9 L 151.5,9.7 L 151.5,31.2 L 168.5,16.0 L 173.0,25.7 L 132.0,82.6 L 152.5,70.8 L 154.0,72.2 L 157.0,79.8 L 158.0,82.6 L 160.0,90.9 L 163.5,96.4 L 187.0,118.7 L 193.0,136.0 L 192.5,138.1 L 185.0,150.6 L 175.0,161.0 L 168.5,160.3 L 157.0,154.0 L 148.0,152.7 L 136.0,123.5 L 130.5,104.8 L 128.0,104.8 L 125.5,103.4 L 123.5,103.4 L 122.0,103.4 L 120.0,101.3 L 116.5,102.7 L 109.0,106.9 L 101.5,108.2 L 99.0,102.7 L 91.0,99.9 L 83.0,94.4 L 78.0,86.7 Z',
        'A8':'M 107.0,41.6 L 103.5,22.2 L 107.5,11.8 L 113.0,6.2 L 115.5,4.9 L 121.0,4.2 L 128.0,7.6 L 134.0,15.3 L 139.5,39.6 L 145.5,36.1 L 151.5,35.4 L 157.5,37.5 L 162.0,41.6 L 165.5,46.5 L 166.5,48.6 L 168.5,56.2 L 168.5,64.5 L 166.5,72.2 L 163.5,79.1 L 158.0,84.7 L 150.0,87.4 L 148.0,127.7 L 147.5,142.9 L 142.0,152.0 L 140.0,153.3 L 134.5,153.3 L 127.5,149.9 L 121.5,140.9 L 106.0,152.7 L 97.5,152.7 L 93.5,149.9 L 90.5,145.7 L 87.0,135.3 L 89.0,120.0 L 126.0,80.5 Z',
        'A9':'M 82.5,82.6 L 86.5,74.9 L 91.0,64.5 L 93.0,55.5 L 97.5,45.8 L 100.5,38.9 L 104.0,33.3 L 108.0,23.6 L 111.0,14.6 L 116.0,7.6 L 119.5,11.1 L 127.0,16.7 L 137.0,24.3 L 139.0,26.4 L 154.0,44.4 L 158.0,44.4 L 159.0,47.9 L 160.5,56.2 L 161.5,61.1 L 185.5,63.8 L 186.5,68.0 L 188.5,83.3 L 188.5,86.0 L 178.5,92.3 L 169.5,97.8 L 161.5,99.9 L 156.0,102.0 L 151.5,108.2 L 151.0,114.5 L 151.5,127.0 L 148.5,129.1 L 146.5,131.8 L 139.0,135.3 L 133.5,140.2 L 128.0,142.9 L 121.5,146.4 L 113.5,150.6 L 103.5,156.1 L 95.5,159.6 L 90.0,154.0 L 86.5,146.4 L 80.5,134.6 L 78.0,122.1 L 78.5,114.5 L 80.0,103.4 L 81.0,93.0 Z',
        'A10':'M 115.0,80.5 L 114.5,75.6 L 113.0,74.2 L 116.0,68.0 L 116.5,61.8 L 116.5,55.5 L 117.0,47.9 L 118.0,37.5 L 119.0,22.2 L 121.0,11.8 L 125.0,18.0 L 135.0,22.2 L 137.5,29.1 L 142.5,32.6 L 151.0,35.4 L 151.0,40.9 L 156.0,39.6 L 159.0,47.9 L 164.0,55.5 L 166.5,54.8 L 126.5,142.2 L 116.0,156.1 L 114.5,155.4 L 109.5,149.9 L 111.5,130.4 L 112.5,118.7 L 113.0,109.6 L 113.5,102.7 L 113.5,97.1 L 114.0,92.3 L 114.5,88.1 Z',
        'A11':'M 74.5,70.1 L 76.0,63.8 L 79.0,47.2 L 80.0,40.2 L 84.0,25.7 L 86.5,16.0 L 88.5,11.8 L 94.5,6.2 L 121.5,47.2 L 126.5,43.7 L 130.5,41.6 L 134.0,39.6 L 138.5,36.8 L 140.5,35.4 L 149.0,30.5 L 156.5,25.7 L 163.5,26.4 L 171.5,27.1 L 179.5,31.2 L 189.0,35.4 L 195.5,41.6 L 195.5,44.4 L 190.0,59.0 L 153.5,77.0 L 152.0,81.9 L 154.5,86.0 L 158.0,92.3 L 168.0,104.1 L 175.5,120.7 L 175.5,129.8 L 170.5,143.6 L 167.5,152.0 L 165.0,152.0 L 144.0,110.3 L 137.5,107.6 L 137.0,107.6 L 134.5,104.8 L 132.0,104.1 L 128.5,102.7 L 127.5,101.3 L 123.5,99.9 L 120.5,99.2 L 117.5,97.8 L 110.0,99.2 L 85.5,107.6 L 78.5,100.6 L 74.5,90.2 L 74.0,86.7 Z',
        'A12':'M 74.5,74.9 L 73.5,63.1 L 73.5,51.3 L 73.5,38.2 L 74.5,23.6 L 78.5,13.2 L 83.0,13.2 L 93.0,13.2 L 103.0,13.9 L 114.0,14.6 L 119.0,14.6 L 128.0,15.3 L 135.5,16.0 L 142.0,16.7 L 151.5,18.0 L 159.0,19.4 L 165.0,20.8 L 173.5,25.0 L 181.0,32.6 L 184.5,34.7 L 192.0,45.8 L 192.0,51.3 L 188.5,64.5 L 184.5,79.1 L 180.0,86.7 L 158.0,104.8 L 157.5,111.0 L 157.5,119.3 L 161.0,136.0 L 161.0,149.9 L 155.5,157.5 L 150.0,157.5 L 145.5,154.0 L 138.5,149.9 L 126.5,149.9 L 119.5,154.0 L 116.0,153.3 L 112.5,149.9 L 110.0,138.8 L 110.0,125.6 L 112.5,112.4 L 111.5,102.7 L 110.5,98.5 L 109.0,94.4 L 108.5,89.5 L 108.5,88.8 Z',
        'A13':'M 191.0,84.7 L 131.5,42.3 L 131.5,33.3 L 136.5,17.3 L 140.0,10.4 L 159.5,17.3 L 166.0,17.3 L 176.0,30.5 L 186.5,33.3 L 190.5,30.5 L 197.0,30.5 L 200.5,24.3 L 208.0,19.4 L 218.0,21.5 L 232.0,12.5 L 237.0,13.9 L 243.0,19.4 L 248.5,30.5 L 252.5,47.2 L 253.0,50.0 L 245.5,65.2 L 220.5,79.8 L 217.5,86.7 L 216.5,93.7 L 217.5,99.2 L 228.0,113.8 L 233.5,129.1 L 236.5,140.2 L 229.0,146.4 L 222.0,156.8 L 221.5,158.2 L 211.5,159.6 L 205.5,159.6 L 196.0,127.7 L 192.0,99.2 L 191.0,90.2 L 191.0,89.5 L 191.0,88.1 L 191.0,86.7 L 191.0,86.0 L 188.5,86.7 L 191.0,85.3 Z',
        'A14':'M 134.5,86.7 L 148.0,79.8 L 158.5,72.9 L 160.5,71.5 L 166.5,68.0 L 167.5,61.1 L 167.5,52.7 L 167.0,40.2 L 169.5,30.5 L 173.5,23.6 L 178.0,18.7 L 201.5,19.4 L 205.5,24.3 L 210.0,31.2 L 213.5,38.9 L 240.0,62.4 L 246.5,74.2 L 246.5,77.7 L 246.5,88.8 L 244.5,97.8 L 240.0,107.6 L 230.5,112.4 L 204.0,101.3 L 201.5,105.5 L 200.0,111.0 L 201.5,122.8 L 199.0,127.0 L 198.0,127.7 L 194.0,127.0 L 187.0,123.5 L 183.0,127.0 L 177.0,136.7 L 170.5,141.6 L 163.5,142.9 L 152.0,149.9 L 139.0,155.4 L 137.5,154.0 L 134.5,142.2 L 130.5,127.0 L 129.5,119.3 L 127.0,98.5 L 126.5,95.8 Z',
        'A15':'M 102.0,75.6 L 99.5,66.6 L 97.5,58.3 L 97.5,51.3 L 94.5,42.3 L 95.5,32.6 L 98.5,20.8 L 104.5,16.0 L 107.5,8.3 L 114.5,3.5 L 116.5,3.5 L 124.0,6.2 L 131.0,9.0 L 136.5,13.9 L 141.5,20.8 L 145.0,28.4 L 147.0,36.8 L 149.0,43.7 L 151.0,50.0 L 152.0,54.1 L 153.5,59.0 L 155.5,66.6 L 157.0,71.5 L 158.0,75.6 L 159.5,81.9 L 161.5,88.1 L 163.5,95.8 L 165.5,104.8 L 166.0,114.5 L 165.0,123.5 L 161.5,133.2 L 157.0,140.9 L 152.0,148.5 L 150.5,149.2 L 144.0,150.6 L 135.0,149.9 L 128.5,147.1 L 123.5,140.9 L 118.5,132.5 L 115.0,122.1 L 113.5,117.3 L 111.5,110.3 L 111.5,102.7 L 108.0,97.1 L 106.0,91.6 L 106.0,90.9 L 104.5,85.3 L 102.5,77.7 Z',
        'A16':'M 55.0,75.6 L 60.0,68.7 L 81.5,63.8 L 93.0,60.4 L 102.5,59.7 L 116.5,65.9 L 118.5,65.9 L 122.0,66.6 L 124.0,66.6 L 125.5,66.6 L 127.5,66.6 L 129.0,66.6 L 131.0,70.1 L 132.0,69.4 L 133.5,69.4 L 135.5,68.0 L 138.0,67.3 L 141.0,64.5 L 143.0,68.0 L 187.5,35.4 L 204.5,38.9 L 205.0,39.6 L 198.5,56.9 L 175.5,74.9 L 159.5,81.9 L 153.0,86.7 L 152.0,90.9 L 149.0,93.0 L 146.0,95.1 L 141.5,94.4 L 140.0,95.8 L 138.0,97.1 L 135.5,99.2 L 135.0,103.4 L 132.0,100.6 L 131.5,100.6 L 128.5,105.5 L 128.0,99.9 L 127.0,97.1 L 124.0,96.4 L 124.0,95.8 L 110.0,110.3 L 97.5,116.6 L 73.0,127.7 L 69.5,122.8 L 65.0,106.9 L 62.0,95.8 L 58.5,84.0 Z',
        'A17':'M 80.0,73.6 L 79.0,64.5 L 79.5,61.1 L 83.0,54.8 L 87.5,45.8 L 94.0,42.3 L 104.0,35.4 L 107.0,38.9 L 114.5,34.0 L 117.5,31.9 L 122.5,23.6 L 130.5,18.7 L 137.0,13.9 L 139.5,12.5 L 150.0,9.7 L 152.0,12.5 L 159.0,29.1 L 158.0,34.0 L 161.0,42.3 L 166.5,47.9 L 170.0,59.0 L 169.0,61.1 L 175.0,74.2 L 174.5,74.9 L 180.5,90.9 L 183.0,96.4 L 183.0,109.6 L 181.5,111.7 L 174.0,118.0 L 167.0,122.1 L 162.0,125.6 L 156.5,129.8 L 149.0,134.6 L 143.5,138.1 L 138.0,141.6 L 132.5,145.0 L 125.0,149.2 L 117.5,154.0 L 111.0,155.4 L 109.5,154.0 L 104.5,145.7 L 100.5,137.4 L 93.0,124.2 L 91.0,124.9 L 92.0,113.1 L 88.0,99.2 L 85.5,92.3 L 82.5,83.3 Z',
    };

    // -----------------------------------------------------------------------
    // State
    // -----------------------------------------------------------------------
    const logEntries = [];
    let lastKey  = '';
    let sending  = false;
    const sendQueue = [];
    let svgDrivers = {};     // name → { g, circle, label }
    let trackPathEl = null;

    // -----------------------------------------------------------------------
    // Race state parser
    // -----------------------------------------------------------------------
    function parseRaceState() {
        const scrollbar = document.getElementById('drivers-scrollbar');
        if (!scrollbar) return null;

        const state = { ts: Date.now(), track: null, laps: null, status: null, drivers: [], my_info: null };

        const headerEl = document.querySelector('.drivers-list');
        if (headerEl) {
            const firstLine = (headerEl.innerText || '').split('\n')[0].trim();
            const m = firstLine.match(/^(.+?)\s*[-–]\s*(\d+)\s*laps?\s*[-–]\s*(.+)$/i);
            if (m) { state.track = m[1].trim(); state.laps = parseInt(m[2], 10); state.status = m[3].trim(); }
        }

        scrollbar.querySelectorAll('ul[class*="driver-item"]').forEach((el, idx) => {
            const lines = (el.innerText || '').trim().split('\n').map(l => l.trim()).filter(Boolean);
            if (!lines.length) return;
            const name = lines[0];
            const raw  = lines[1] ? parseFloat(lines[1]) : NaN;
            state.drivers.push({ position: idx + 1, name, completion: isNaN(raw) ? null : raw });
        });

        const wrap = document.querySelector('.track-wrap');
        if (wrap) {
            const txt = wrap.innerText || '';
            const g = (label) => { const m = txt.match(new RegExp(label + '[:\\s]+([^\\n]+)', 'i')); return m ? m[1].trim() : null; };
            state.my_info = { name: g('Name'), position: g('Position'), lap: g('Lap'), last_lap: g('Last Lap'), completion: parseFloat(g('Completion') || '') || null };
        }

        // Grab track image URL and extract code (e.g. "A5" from ".../A5.jpg?v=...")
        const trackImg = document.querySelector('img.img-track');
        if (trackImg && trackImg.src) {
            state.track_img  = trackImg.src;
            const m = trackImg.src.match(/\/([A-Z]\d+)\.jpg/i);
            state.track_code = m ? m[1].toUpperCase() : null;
        }

        return state;
    }

    // -----------------------------------------------------------------------
    // Send to server
    // -----------------------------------------------------------------------
    function record(type, data) {
        logEntries.unshift({ type, ts: Date.now(), data });
        if (logEntries.length > MAX_LOG) logEntries.pop();
        renderAll();
        enqueue({ type, ts: Date.now(), data });
    }

    function enqueue(entry) {
        sendQueue.push(entry);
        if (!sending) flush();
    }

    function flush() {
        if (!sendQueue.length) { sending = false; return; }
        sending = true;
        GM_xmlhttpRequest({
            method: 'POST', url: SERVER,
            headers: { 'Content-Type': 'application/json' },
            data: JSON.stringify(sendQueue.splice(0, 10)),
            onload:  () => flush(),
            onerror: () => { setPillStatus('server offline', '#f80'); setTimeout(flush, 3000); },
        });
    }

    // -----------------------------------------------------------------------
    // Observer + polling
    // -----------------------------------------------------------------------
    function checkAndSend() {
        const state = parseRaceState();
        if (!state || !state.drivers.length) return;
        const key = state.drivers.map(d => `${d.name}:${d.completion}`).join('|');
        if (key === lastKey) return;
        lastKey = key;
        record('race_state', state);
    }

    let observerAttached = false;
    setInterval(() => {
        checkAndSend();
        if (!observerAttached) {
            const target = document.getElementById('drivers-scrollbar');
            if (target) {
                new MutationObserver(checkAndSend).observe(target, { childList: true, subtree: true, characterData: true });
                observerAttached = true;
                setPillStatus('watching', '#0f0');
            }
        }
    }, 1000);

    // -----------------------------------------------------------------------
    // Build UI
    // -----------------------------------------------------------------------
    let pill = null, panel = null, panelOpen = false;

    function buildUI() {
        // Pill
        pill = el('div', {
            style: `position:fixed;bottom:12px;right:12px;z-index:2147483647;
                    background:#111;color:#888;border:1px solid #444;
                    padding:5px 14px;border-radius:20px;font-size:12px;
                    font-family:monospace;cursor:pointer;user-select:none;`,
            textContent: '⬤ RacingSpy',
            onclick: togglePanel,
        });
        document.body.appendChild(pill);

        // Panel
        panel = el('div', {
            style: `position:fixed;bottom:48px;right:12px;z-index:2147483646;
                    width:500px;background:#0d0d0d;border:1px solid #0f0;
                    border-radius:8px;font-family:monospace;font-size:11px;
                    display:none;box-shadow:0 4px 24px rgba(0,255,0,.12);`,
        });

        // Header bar
        const hdr = el('div', {
            style: `padding:7px 12px;background:#111;border-bottom:1px solid #0f0;
                    display:flex;justify-content:space-between;align-items:center;
                    border-radius:8px 8px 0 0;`,
        });
        hdr.innerHTML = `
            <span style="color:#0f0;font-weight:bold;font-size:12px">⬤ RacingSpy</span>
            <span id="_spy_header_info" style="color:#888;font-size:11px"></span>
            <button id="_spy_close" style="background:#1a1a1a;color:#888;border:1px solid #333;
                border-radius:4px;padding:2px 8px;cursor:pointer;font-size:11px;">✕</button>
        `;
        panel.appendChild(hdr);

        // Body: map (left) + leaderboard (right)
        const body = el('div', { style: 'display:flex;padding:10px;gap:10px;' });

        // --- SVG map ---
        // Wrapper is position:relative so the img and SVG stack correctly
        const mapWrap = el('div', {
            style: `flex:0 0 auto;position:relative;width:${MAP_W}px;height:${MAP_H}px;
                    border-radius:6px;overflow:hidden;background:#111;border:1px solid #1a1a1a;`,
        });

        // Real track image — plain <img> absolutely behind the SVG
        const trackImgEl = el('img', {
            style: `position:absolute;top:0;left:0;width:100%;height:100%;
                    object-fit:contain;display:none;`,
        });
        trackImgEl.id = '_spy_track_img';
        mapWrap.appendChild(trackImgEl);

        // SVG sits on top, transparent background so the img shows through
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('viewBox', `0 0 ${MAP_W} ${MAP_H}`);
        svg.setAttribute('width', MAP_W);
        svg.setAttribute('height', MAP_H);
        svg.style.cssText = 'position:absolute;top:0;left:0;display:block;';

        // Fallback oval fill (shown when no track image yet)
        const trackFill = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        trackFill.id = '_spy_track_fill';
        trackFill.setAttribute('d', FALLBACK_PATH);
        trackFill.setAttribute('fill', '#161616');
        trackFill.setAttribute('stroke', 'none');
        svg.appendChild(trackFill);

        // Fallback oval outline
        const trackOutline = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        trackOutline.id = '_spy_track_outline';
        trackOutline.setAttribute('d', FALLBACK_PATH);
        trackOutline.setAttribute('fill', 'none');
        trackOutline.setAttribute('stroke', '#2a5a2a');
        trackOutline.setAttribute('stroke-width', '12');
        trackOutline.setAttribute('stroke-linejoin', 'round');
        svg.appendChild(trackOutline);

        // Path element — invisible, used only for getPointAtLength() maths
        const trackLine = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        trackLine.id = '_spy_track_path';
        trackLine.setAttribute('d', FALLBACK_PATH);
        trackLine.setAttribute('fill', 'none');
        trackLine.setAttribute('stroke', 'none');
        svg.appendChild(trackLine);
        trackPathEl = trackLine;

        // Start/finish marker (visible in fallback mode)
        const sfLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        sfLine.id = '_spy_sf_line';
        sfLine.setAttribute('x1', '118'); sfLine.setAttribute('y1', '150');
        sfLine.setAttribute('x2', '142'); sfLine.setAttribute('y2', '160');
        sfLine.setAttribute('stroke', '#fff');
        sfLine.setAttribute('stroke-width', '2');
        svg.appendChild(sfLine);

        // Driver layer (circles go here, on top of track)
        const driverLayer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        driverLayer.id = '_spy_driver_layer';
        svg.appendChild(driverLayer);

        mapWrap.appendChild(svg);
        body.appendChild(mapWrap);

        // --- Leaderboard ---
        const lb = el('div', { id: '_spy_lb', style: 'flex:1;overflow:hidden;' });
        body.appendChild(lb);

        panel.appendChild(body);

        // Footer
        const footer = el('div', { id: '_spy_footer', style: 'padding:5px 12px 8px;color:#444;font-size:10px;border-top:1px solid #1a1a1a;' });
        panel.appendChild(footer);

        document.body.appendChild(panel);
        document.getElementById('_spy_close').addEventListener('click', () => { panelOpen = false; panel.style.display = 'none'; });
    }

    // -----------------------------------------------------------------------
    // Render
    // -----------------------------------------------------------------------
    function renderAll() {
        if (!pill) return;
        const updates = logEntries.filter(e => e.type === 'race_state').length;
        pill.textContent = `⬤ RacingSpy [${updates}]`;
        pill.style.color  = '#0f0';
        pill.style.border = '1px solid #0f0';

        if (!panelOpen) return;

        const latest = logEntries.find(e => e.type === 'race_state');
        if (!latest) return;

        renderMap(latest.data);
        renderLeaderboard(latest.data);
        renderFooter(latest.data);
    }

    function renderMap(state) {
        if (!trackPathEl) return;
        const layer = document.getElementById('_spy_driver_layer');
        if (!layer) return;

        // Swap in the correct per-track path for getPointAtLength() maths
        if (state.track_code && trackPathEl) {
            const d = TRACK_PATHS[state.track_code] || FALLBACK_PATH;
            if (trackPathEl.getAttribute('d') !== d) {
                trackPathEl.setAttribute('d', d);
                svgDrivers = {}; // reset dots so they're recreated at correct positions
                document.getElementById('_spy_driver_layer').innerHTML = '';
            }
        }

        // Swap in the real track image when available; hide fallback oval
        if (state.track_img) {
            const imgEl = document.getElementById('_spy_track_img');
            if (imgEl && imgEl.src !== state.track_img) {
                imgEl.src = state.track_img;
                imgEl.style.display = 'block';
                const fill    = document.getElementById('_spy_track_fill');
                const outline = document.getElementById('_spy_track_outline');
                const sf      = document.getElementById('_spy_sf_line');
                if (fill)    fill.style.display    = 'none';
                if (outline) outline.style.display = 'none';
                if (sf)      sf.style.display      = 'none';
            }
        }

        const totalLen = trackPathEl.getTotalLength();
        const myName   = state.my_info?.name;

        state.drivers.forEach((d, idx) => {
            const pct   = (d.completion ?? 0) / 100;
            const pt    = trackPathEl.getPointAtLength(pct * totalLen);
            const color = COLORS[idx % COLORS.length];
            const isMe  = d.name === myName;

            let g = svgDrivers[d.name]?.g;

            if (!g) {
                // Create group for this driver
                g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
                g.style.transition = 'transform 0.7s ease-out';

                const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                circle.setAttribute('r', isMe ? '7' : '5');
                circle.setAttribute('fill', color);
                circle.setAttribute('stroke', isMe ? '#fff' : '#000');
                circle.setAttribute('stroke-width', isMe ? '2' : '1');

                const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                label.setAttribute('text-anchor', 'middle');
                label.setAttribute('dy', '0.35em');
                label.setAttribute('font-size', '7');
                label.setAttribute('font-family', 'monospace');
                label.setAttribute('fill', isMe ? '#000' : '#fff');
                label.setAttribute('font-weight', 'bold');
                label.setAttribute('pointer-events', 'none');
                label.textContent = String(d.position);

                // Tooltip: driver name on hover
                const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
                title.textContent = `${d.name} — ${d.completion?.toFixed(1) ?? '?'}%`;

                g.appendChild(circle);
                g.appendChild(label);
                g.appendChild(title);
                layer.appendChild(g);

                svgDrivers[d.name] = { g, circle, label };
            }

            // Update label and completion tooltip
            svgDrivers[d.name].label.textContent = String(d.position);
            const titleEl = g.querySelector('title');
            if (titleEl) titleEl.textContent = `${d.name} — ${d.completion?.toFixed(1) ?? '?'}%`;

            // Animate to new position
            g.setAttribute('transform', `translate(${pt.x.toFixed(1)}, ${pt.y.toFixed(1)})`);
        });

        // Remove drivers no longer in the race
        for (const name of Object.keys(svgDrivers)) {
            if (!state.drivers.find(d => d.name === name)) {
                svgDrivers[name].g.remove();
                delete svgDrivers[name];
            }
        }
    }

    function renderLeaderboard(state) {
        const lb = document.getElementById('_spy_lb');
        if (!lb) return;
        const myName = state.my_info?.name;

        let html = '';
        state.drivers.forEach((d, idx) => {
            const color  = COLORS[idx % COLORS.length];
            const isMe   = d.name === myName;
            const pct    = d.completion ?? 0;
            const barW   = Math.round(pct / 100 * 80);  // max 80px
            const name   = d.name.length > 14 ? d.name.slice(0, 13) + '…' : d.name;
            html += `
                <div style="margin-bottom:5px;">
                    <div style="display:flex;align-items:center;gap:5px;margin-bottom:2px;">
                        <span style="color:${color};font-size:9px;">●</span>
                        <span style="color:${isMe ? '#ffaa00' : '#ccc'};flex:1;overflow:hidden;white-space:nowrap;">
                            ${d.position}. ${name}${isMe ? ' ★' : ''}
                        </span>
                        <span style="color:#888;font-size:10px;">${d.completion != null ? d.completion.toFixed(2) + '%' : '?'}</span>
                    </div>
                    <div style="background:#1a1a1a;border-radius:2px;height:3px;width:100%;">
                        <div style="background:${color};height:3px;width:${barW}px;border-radius:2px;transition:width 0.7s ease-out;"></div>
                    </div>
                </div>`;
        });
        lb.innerHTML = html;
    }

    function renderFooter(state) {
        const footer = document.getElementById('_spy_footer');
        if (!footer) return;
        const mi = state.my_info || {};
        const imgStatus = state.track_img
            ? `img: ${state.track_img.split('/').pop()}`
            : 'img: not found — check selector';
        footer.innerHTML = `
            <div>Lap ${mi.lap ?? '?'} &nbsp;·&nbsp; Last lap ${mi.last_lap ?? '?'} &nbsp;·&nbsp; Position ${mi.position ?? '?'}</div>
            <div style="color:#333;margin-top:2px;">${imgStatus}</div>
        `;
    }

    // -----------------------------------------------------------------------
    // Helpers
    // -----------------------------------------------------------------------
    function togglePanel() {
        panelOpen = !panelOpen;
        panel.style.display = panelOpen ? 'block' : 'none';
        if (panelOpen) renderAll();
    }

    function setPillStatus(status, color) {
        if (!pill) return;
        pill.textContent  = `⬤ RacingSpy — ${status}`;
        pill.style.color  = color;
        pill.style.border = `1px solid ${color}`;
    }

    function el(tag, props = {}) {
        const e = document.createElement(tag);
        Object.entries(props).forEach(([k, v]) => {
            if (k === 'style')   e.style.cssText = v;
            else if (k === 'onclick') e.addEventListener('click', v);
            else e[k] = v;
        });
        return e;
    }

    // -----------------------------------------------------------------------
    // Boot
    // -----------------------------------------------------------------------
    function boot() {
        try {
            buildUI();
            setPillStatus('waiting for race', '#888');
            record('connected', { href: location.href });
        } catch (e) {
            console.error('[RacingSpy] boot error:', e);
            // Emergency pill so errors are visible
            const ep = document.createElement('div');
            ep.style.cssText = 'position:fixed;bottom:12px;right:12px;z-index:2147483647;background:#600;color:#f88;border:1px solid #f44;padding:5px 12px;border-radius:20px;font-size:11px;font-family:monospace;';
            ep.textContent = 'RacingSpy ERROR — check console';
            document.body.appendChild(ep);
        }
    }

    document.body ? boot() : document.addEventListener('DOMContentLoaded', boot);

})();
