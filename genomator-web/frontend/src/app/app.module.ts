import { NgModule } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { AppRoutingModule } from './app-routing.module';
import { AppComponent } from './app.component';

import { MatTabsModule } from '@angular/material/tabs';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { NavBarComponent } from './nav-bar/nav-bar.component'; // Import the NavBarComponent
import { FooterComponent } from './footer/footer.component';
import { FontAwesomeModule } from '@fortawesome/angular-fontawesome'; // Import the FooterComponent




@NgModule({
  declarations: [
    AppComponent,
    NavBarComponent, // Declare the NavBarComponent here
    FooterComponent,
  ],
  imports: [
    BrowserModule,
    AppRoutingModule,
    MatTabsModule,
    BrowserAnimationsModule,
    FontAwesomeModule,
    
    // NgParticlesModule, // Include NgParticlesModule here

  ],
  providers: [
  ],
  bootstrap: [AppComponent]
})
export class AppModule { }
