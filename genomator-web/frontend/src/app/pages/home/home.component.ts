import { Component, OnInit } from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { FontAwesomeModule } from '@fortawesome/angular-fontawesome';
import { faGithub } from '@fortawesome/free-brands-svg-icons';
import { faFileLines } from '@fortawesome/free-solid-svg-icons';
import { faDna } from '@fortawesome/free-solid-svg-icons';
import { faBook } from '@fortawesome/free-solid-svg-icons';
import { faArrowUpRightFromSquare } from '@fortawesome/free-solid-svg-icons';

@Component({
  host: {'class': 'page-content'},
  selector: 'app-home',
  standalone: true,
  imports: [
    RouterLink,
    FontAwesomeModule
  ],
  templateUrl: './home.component.html',
  styleUrls: ['./home.component.css']
})
export class HomeComponent implements OnInit {
  faGithub = faGithub;
  faFileLines = faFileLines;
  faDna = faDna;
  faBook = faBook;

  ngOnInit() {
    window.scrollTo(0, 0);
  }

  constructor(private router: Router) { }

  redirect(location:string) {
    document.location = location;
  }

}
