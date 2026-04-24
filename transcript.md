[00:00:00] Okay, so this is a client.
[00:00:05] portal client-facing website that we have currently which we are trying to migrate
[00:00:10] To our new portal, which is OneWeb. So, this portal currently hands
[00:00:15] Our tax relief clients, that's the name we have, for our investigation and resolution.
[00:00:20] clients and this is the home page currently for the client portal.
[00:00:25] And in the home page, we have a status bar showing where they stand.
[00:00:30] As per our services, investigation and resolution progress with the status bar.
[00:00:35] And if the client is expected to submit any kind of information.
[00:00:40] To us, and if we are waiting on that, and if you have submitted any information requests to us.
[00:00:45] That vectors, do you have any HLD means what is the
[00:00:50] High-level view of this application: are there multiple applications under one umbrella?
[00:00:55] And this is the one application we are talking about. So I will get a good idea. That's right.
[00:01:00] if that is an enterprise application do we have any diagram sort of thing
[00:01:05] No, I don't think we have a uh uh architectural diagram. I know what you're referring to.
[00:01:10] to this is the website prashant which if facing customers
[00:01:15] Customers and the back end, the services are directly connected.
[00:01:20] there's two services two types of services one that is totally independent uh website we can say
[00:01:25] That's what I'm saying. I'm about to come there. Mostly it's independent, it's connected.
[00:01:30] To its own database, but there are some services which are which are connecting to sales.
[00:01:35] Okay, so these are the third parties. Okay.
[00:01:40] Salesforce is also internally used application. This is customer facing website, right?
[00:01:45] But if a customer enrolls in an investigation, how do our agents know about it?
[00:01:50] Salesforce is an application, all our internal employees use our agents, you know, you know.
[00:01:55] customer facing, customer service members, on lawyer attorneys, I was talking about tax preparers.
[00:02:00] They all use Salesforce. So all the data.
[00:02:05] all the data from this is synced into Salesforce database so that they
[00:02:10] will have access and they'll have the same understanding what's happening on this website.
[00:02:15] But I would say as I said like mostly it's independent but only thinking part.
[00:02:20] Okay.
[00:02:25] Yeah. So as Pankat said, this is a sales force where our internal agents use.
[00:02:30] and they you know they progress on the cases in in Salesforce.
[00:02:35] while this is a view for our clients to see where they stand yeah and what
[00:02:40] Whatever information that we request to the client, the agents might be doing it from sales.
[00:02:45] are right yeah customers customers for optima okay cool
[00:02:50] Okay. Yeah. Yeah. Clients are yeah. We can we call clients, members, customers.
[00:02:55] The same thing, right? So I think we need to work.
[00:03:00] it's the first time right Lakshmi. So when they are enrolling into the account, Prashant?
[00:03:05] For example, you know, they say, okay, we owe $50,000 to IRS, right?
[00:03:10] Then we sell them as part of the investigation. They pay us $495.
[00:03:15] And they enroll into investigation canal. But as per
[00:03:20] The investigation, we need information from them, right? They have to send them and send us all their.
[00:03:25] Documents they have. Okay. But as part of document.
[00:03:30] Collection: if something is missing. So, what our agents do is they
[00:03:35] They send a request called information request. That's what Lakshmi is walking you through.
[00:03:40] So in Salesforce, agents, when they see, okay, this new customer enrolled.
[00:03:45] they'll see all the documents which they submitted, which Lakshmi is showing right now.
[00:03:50] they if they see anything is missing then they'll create
[00:03:55] Information request. Can you do that now? One information request. Yeah, for example. So right now she clicks.
[00:04:00] To add new request right on the top, right.
[00:04:05] And then you can select the map.
[00:04:10] any whatever information that you are in need from the client
[00:04:15] from this drop-down list and then hit save that will create an information request to the client
[00:04:20] and when the client log into the client portal which is their website they should be able to see that
[00:04:25] information that we requested to them. I'll just show you right now.
[00:04:30] If they go to this request tab under their website is where they will see all the
[00:04:35] requested information from Optima. So it has a quite a few bits.
[00:04:40] I had already submitted and the CTU is the current one which I did right now.
[00:04:45] Okay.
[00:04:50] So yeah, out of all the staffs uh we uh prefer to migrate information records.
[00:04:55] First, to OneWeb as a top priority. Apart from
[00:05:00] We have a payments tab just giving an overview under payments tab as Banka does.
[00:05:05] Said, right, there are two services. First one will be the investigation where
[00:05:10] where we collect all their information and do the initial investigation.
[00:05:15] And then after that, they will enter the resolution. So the payments tab will show.
[00:05:20] Their payment schedules for each of the investigation and the
[00:05:25] solution and whatever amount they owe and they can even pay from using this pay now.
[00:05:30] button under payments tab and under services they can see
[00:05:35] all the enrollment documents that when while they do the enrollment right and sign up for the enrollment
[00:05:40] investigation, all the documents that they sign, they can view under here.
[00:05:45] thing for the resolution when they enroll and sign up they can view all the documents
[00:05:50] That's signed as part of the enrollment channel. And the third and the fifth tab is the document.
[00:05:55] tab where they can upload any random document which they want to submit to
[00:06:00] Optima, apart from the request, even if nothing is requested, they are.
[00:06:05] able to submit anything using here using this upload button.
[00:06:10] So these are the features that we need to migrate from client portal to one web starting.
[00:06:15] with information request. And there are around
[00:06:20] 29 to 30 in different type of information because as I was showing you here, right.
[00:06:25] that we need to migrate and each of them might have a different logic behind it.
[00:06:30] So, all these. For example, if I show you here.
[00:06:35] If you look at the tax return, you see an upload button.
[00:06:40] Here so when the clients come and click here to provide the tax return, how it works.
[00:06:45] is they will be able to browse and upload a document from their local drive.
[00:06:50] And that's one way, one type of information request, which is an upload, and there are other forms.
[00:06:55] like you know the income and expense that's kind of a temporary
[00:07:00] that they should be able to complete within client portal itself.
[00:07:05] By moving from one page to another, they can fill in all the info here itself.
[00:07:10] There are other two types which are wet sign and e-sign. For example,
[00:07:15] Here it says sign and return. So, if they hit here, they should be able to.
[00:07:20] print the document, wet sign it, and then upload it back. That's the way they will be submitting.
[00:07:25] wet sign information request to us and the fourth one is eSign they should
[00:07:30] be able to e-sign in the portal itself for the for all the e-sign
[00:07:35] information because so we don't have too many uh e-sign uh and web sign uh
[00:07:40] Think power of attorney and tax information authorization are the two information requests which they
[00:07:45] Can do via e-sign from the client portal, and same with the website.
[00:07:50] Those are the two documents they can do via wet sign. But all the others,
[00:07:55] come under either as a template or by uploading from the
[00:08:00] And so we pay for that.
[00:08:05] I think excuse me, let's hold on, let's not go that fast because it's you know
[00:08:10] actually it understands the first time you're seeing everything. So you understand that uh all right, Prashant?
[00:08:15] Yeah, so far.
[00:08:20] So, all we are focusing right now is this post, this module, information request.
[00:08:25] the different types and we will start migrating one type at a time.
[00:08:30] At a time to the new website, new application, which is the
[00:08:35] developed in React and.NET, I mentioned, right?
[00:08:40] I think you're pretty familiar. Each request is different type. It might have a
[00:08:45] Pop up, it might have a couple of pages. That's the only difference. Yeah. Yeah.
[00:08:50] And behind every page, obviously, there'll be a service. Like, you know, I think PHP services.
[00:08:55] they might have written in PHP or Python.
[00:09:00] We have to see. We'll provide the prototype. You'll be able to understand that.
[00:09:05] Okay. Any questions so far?
[00:09:10] No, it's looks good. It means we have some specific type based on that.
[00:09:15] This list is getting populated, whatever the request we raised.
[00:09:20] Right. And once you start to start working on that specific
[00:09:25] Block that entire flow is different for each block. Maybe there are some pages.
[00:09:30] For some may have some pop-ups. Right. So based on some basic type.
[00:09:35] Maybe there. Based on that, entire thing is happening. Okay.
[00:09:40] Pretty straightforward, right? Agent and sales force are reviewing the case, they will ask different information.
[00:09:45] And as soon as they submit the request in Salesforce, this is the client.
[00:09:50] Facing portal, right? They will see that request, and the customer is supposed to fulfill the.
[00:09:55] Request as simple as that. So the dog request comes from here and
[00:10:00] And the documents are provided on the portal. And it'll go back to Salesforce.
[00:10:05] Force. That's where the connection is for the Salesforce. You mentioned, right? Is it independent?
[00:10:10] It's independent only to a sense where you can enroll, but all this data has to be flowing to say.
[00:10:15] So that agents can see it. Okay. And those APIs are already.
[00:10:20] there. So we will discuss as part of the migration. We can keep them.
[00:10:25] As is, or convert them into.NET if they're not already there. Okay. Okay. Yeah.
[00:10:30] It might be simpler to start with, you know, we migrate only the portal side.
[00:10:35] Any connection to Salesforce will leave as is. That's also an easy step.
[00:10:40] First step, then later we can convert those connections into C sharp.
[00:10:45] Okay, yeah.
[00:10:50] All like five tabs, but each tab, if you dig into it, it might have multiple.
[00:10:55] pages that's all okay and let me show you in salesforce prashan so you
[00:11:00] you will understand what Benkat just said. So this is the information tab in Salesforce where
[00:11:05] They are able to submit a new one, right? So if you look at the type here,
[00:11:10] Document is the one type, and you can also see e-sign and wet sign. So, if we select eSign.
[00:11:15] There are only two types of document that you can submit as e-sign, and that will have one.
[00:11:20] One flow when it comes to client portal, right? How submitting it is in one flow. And then
[00:11:25] Then wetsign is the next kind which has also two other types.
[00:11:30] of documents and they both follow the same path how when they submitted from client portal
[00:11:35] And majority of the information requests are under documents, and here.
[00:11:40] is where they have this start form, either start form or upload.
[00:11:45] directly uploading a document or they'll be finishing it.
[00:11:50] By populating each forms within the client portal itself. So, those all are coming.
[00:11:55] Under documents type. And one other thing.
[00:12:00] So you can see here their status shows a spending right for the
[00:12:05] The information request when it's submitted. So if you look at the client border, the clients will be able to.
[00:12:10] See how many requests are pending for each of them. And then once they start doing.
[00:12:15] It will move from review to completed. So eventually, once they finish one request, it will move to.
[00:12:20] Completed in their client portal, and the same count will be updated in Salesforce as.
[00:12:25] Well, it will be showing us completed instead of pending.
[00:12:30] Like here, it will become completed.
[00:12:35] Collected, so not completed. Here it's collected.
[00:12:40] Now I can show you the one.
[00:12:45] web the other portal where we are trying to migrate this request center tab
[00:12:50] right from client portal okay so this is a one web
[00:12:55] Can you go to the home page and log in from there so that Hila understands?
[00:13:00] One web? Yeah. Go to homepage and start from there.
[00:13:05] Right now there is no home page with that's something which we are adding.
[00:13:10] Are new? Right there, right? This is a signing page, right? First, they have to.
[00:13:15] Yeah, this is the first page.
[00:13:20] login page Prashant. So create account which is
[00:13:25] which is not part of the scope, that's a different flow. But once the account is created, they log in.
[00:13:30] And once they log in, you know, they're that the authentication is happening right now.
[00:13:40] Okay, once you log in, this is what the clients will see. Right now, we
[00:13:45] have tax preparation and tax shield so we don't have a home page or
[00:13:50] For tax relief, of course, tax relief is in client portal here, right? That's the reason why.
[00:13:55] So when we migrate, our business stakeholders prefer to have a home page.
[00:14:00] And home page will be the landing page for the clients when they log in.
[00:14:05] And we will be adding a tax relief as a third option, apart from tax preparation and tax shield.
[00:14:10] I can show you the mock-ups we have. Yeah, very good.
[00:14:15] Okay.
[00:14:20] Have for our migration. As you can see here, there will be a home tab.
[00:14:25] On the top of the left-hand side menu, and then tax relief is something new that.
[00:14:30] we'll be adding and where we'll be displaying some of the tabs that we migrate from client portal.
[00:14:35] to one web tax shield is existing current tax shield
[00:14:40] One other change will be: as you can see here, in OneWeb, documents is one of the sub.
[00:14:45] menu on the tax shield currently. We will be pulling that out of tax shield and making it as a main
[00:14:50] Menu because that documents will be used by both our client attack shield and.
[00:14:55] Tax relief clients which we migrate and the current.
[00:15:00] Yeah, go ahead, Prashant. And sorry, go ahead. Okay.
[00:15:05] And that the information requests.
[00:15:10] The first tab that we are trying to migrate, we want this information.
[00:15:15] Information requests or information center to be displayed within.
[00:15:20] the documents. Let me show you that.
[00:15:25] So, what is the home page? Has looks like the home page has something, right? Yeah.
[00:15:30] Has the current home page, right? In the client portal.
[00:15:35] What they're currently showing client portal is the
[00:15:40] Status bar specifically for our tax relief and then.
[00:15:45] There will be this help section on the right-hand side, and if any information.
[00:15:50] Spending that will also be shown in the home page, and then when we migrate.
[00:15:55] rate, we are creating a tax relief option separately, right?
[00:16:00] Business prefers to move that status bar inside tax relief overview.
[00:16:05] Homepage because that's specific to tax relief. And in the home page, we'll be showing.
[00:16:10] whatever information requests are pending for the client, either for tax relief or tax shield.
[00:16:15] Any information requested and the help section.
[00:16:20] To be created first, then, as part of the first migration, right? Yeah, home.
[00:16:25] Home and information request kind of goes together because so we need to get together.
[00:16:30] that scope so we need to change the left side menu prashant as part of the first migration
[00:16:35] Then go to the home page and migrate this.
[00:16:40] Portion, this functionality here, then the information request first set.
[00:16:45] So there's three steps. First change the left side menu, create a home page.
[00:16:50] and the third information request under the documents which is going to walk you through can you expand
[00:16:55] The document when you work. Yeah, sure. Home.
[00:17:00] Page and then the tax relief. Let me show you that too. Under tax relief, we will have an overview.
[00:17:05] overview tab under which we will migrate the status bar as you see here.
[00:17:10] and then um the documents right the documents which we pulled
[00:17:15] out of Tax Shield under documents is where we will have the request center.
[00:17:20] which we migrate from client portal. Here, we need to have
[00:17:25] Three tabs. First one will be the request sender, which will display all the information requests as a
[00:17:30] each block which is submitted from Salesforce and the second one is a file manager.
[00:17:35] tab that is this one so currently whatever the
[00:17:40] Under whatever existing document in one web, right, that has already
[00:17:45] this file manager. Let me show you that so we will understand better.
[00:17:50] So if you click on documents, right, this is the current one web. It has a file manager page.
[00:17:55] this is already existing. So we are keeping that but that will be the
[00:18:00] First one will be request center showing all the pending information requests.
[00:18:05] Second will be the file manager where they can see all the uploaded documents, including the
[00:18:10] Information request, right? When they submit the request, any document they upload as part of it will be.
[00:18:15] Be displayed in the file manager. Okay. Also, any
[00:18:20] Any documents that they upload while as part of the enrollment.
[00:18:25] If they upload any government ID, that will also be displayed here, anything they upload.
[00:18:30] And the third tab is the enrollment docs. Enrollment docs.
[00:18:35] Is actually the let me go back to client porter, the service is.
[00:18:40] Tab here, right? I was showing you here. The services tab usually
[00:18:45] Shows all the documents that they signed as part of the enrollment when they did investigate.
[00:18:50] So instead of services, now we are going to call it and
[00:18:55] Enrollment docs. And we'll have to do it.
[00:19:00] The file manager as well as enrollment documents. Enrollment docs have only the enrollment.
[00:19:05] uh documents but file manager will have any document that client upload as part of the information request too
[00:19:10] Any document they have.
[00:19:15] part of file manager as well no endrollment docs will have all the docs
[00:19:20] documents that they signed as part of the tunnel, but the documents they upload,
[00:19:25] When we do that, upload it. Exactly, yeah. Okay. So you don't log in.
[00:19:30] Documents are basically our legal documents. Correct. Yeah.
[00:19:35] So it's a legal agreement, right? Peshanti, you know, when they enroll, they agree to our terms and conditions.
[00:19:40] Payments and everything. Those are called enrollment documents, which we under.
[00:19:45] That basically those are optimized legal documents if you see client service.
[00:19:50] Name and authorization and the agreement and stuff like that.
[00:19:55] And that will be uh, yeah.
[00:20:00] Any SharePoint right for maybe these documents are very secure.
[00:20:05] S3. So currently that application using S3. Correct. Yeah.
[00:20:10] S3s, all the S3 documents are encrypted, the servers.
[00:20:15] Actually, we were also discussing about having second layer making all
[00:20:20] This files password protection, which is still we are working on it. But right now, all the S3 buckets are in.
[00:20:25] And they're very, very, very personal, like in all the PI data.
[00:20:30] Uh so securities are really critical for this company. Yeah.
[00:20:35] We have to make sure that when we are developing or any displaying any information
[00:20:40] The code has to follow the security standards and the database, whatever.
[00:20:45] Are saving in the database has to be masked properly, and the documents have to be.
[00:20:50] Obviously, all our APIs are encrypted at the rest, end-to-end.
[00:20:55] Including S3. Okay.
[00:21:00] Um looks like a banker currently in the documents one web
[00:21:05] all the uploaded documents and even the agreement goes there when they sign it.
[00:21:10] But when we migrate, we want to spread that out. That's what we see here. That's why we kept.
[00:21:15] File manager and enrollment doc separately. So, all the enrollment documents, including agreement and all.
[00:21:20] All the authorizations will go here and anything that they upload as part of the enrollment will go under.
[00:21:25] File manager. Okay. Yeah. And under Enrollment Docs itself, we
[00:21:30] We separate them as investigation resolution. Even taxial and
[00:21:35] As preparation, we are adding here separately, right? Okay. I think, you know, yeah, so one thing.
[00:21:40] Go step by step. They'll be by the time they go to enrollment documents, I think the first they'll be doing the.
[00:21:45] Request center, right? Yeah. And the file manager or they're
[00:21:50] Doing all the three tabs as the first part of the first migration? First migration.
[00:21:55] They are doing only the request tab. But in order to do that, right, all the
[00:22:00] UI, I think the separation of the tabs, all that, they have it ready, but not the APIs.
[00:22:05] Only on the you know, we should be working only on the request center first, okay? The UI is more.
[00:22:10] Are done, but we have to develop the complete UI first, but on Mega.
[00:22:15] Even not just the mock-up, the UI is also ready.
[00:22:20] this yeah with all these tabs in the in the in the client port in the
[00:22:25] One web. Okay. Yeah. I mean, it's not there in Dev, but locally they have it.
[00:22:30] Completed. Okay, okay. I know we can use it. I don't know.
[00:22:35] We can use it or not, that one, because we're not moving with that directory in the direction.
[00:22:45] And then so that um
[00:22:50] Earlier vendors developed this, right? So, this one web, whatever we are.
[00:22:55] Looking into so they are doing manually now.
[00:23:00] that our thought is go with the yeah with the same purpose.
[00:23:05] whatever they developed, we will keep as is and we will keep extending that.
[00:23:10] Is that the approach? Yeah, there's two options as I said, right? You know, if you want to use GraphQL or not.
[00:23:15] That's only change, but the React, yes, we'll keep the React as is and.
[00:23:20] For example, we have an existing menu, right? Now you'll use AI to make the
[00:23:25] changes I want you know instead of this structure this is a new structure change the you
[00:23:30] React code. Then you'll compile it and upload it. Under each tab.
[00:23:35] Obviously, no. The React part is simple. Keep extending it.
[00:23:40] And the Lambda function part is also
[00:23:45] So okay, only the graphQL part you can decide if you want to keep it and extend it or
[00:23:50] remove the GraphQL altogether and go with like you know traditional entity framework.
[00:24:00] I can't remember.
[00:24:05] said we already have a database tables in place in the new one.
[00:24:10] and the old one we are not deleting anything from the old we'll keep them as is and uh
[00:24:15] We'll be connecting to the same tables then. Yeah, for now. Until we
[00:24:20] merge yeah yeah so even though they're accessing this web uh you are
[00:24:25] Prashant, the services will be still connecting to the whole database.
[00:24:30] Okay. In that way, it actually in that way then it
[00:24:35] MySQL. Okay. You don't have to.
[00:24:40] worry about any database changes then. Even the services that work the services which are connecting to Salesforce.
[00:24:45] They'll be in place. You don't have to change anything. So it will be a much better approach.
[00:24:50] Only working on the UI and the business layer. Got it.
[00:24:55] Um if you look at the next section.
[00:25:00] Payments tab. So, if you see in our current one web, it resides here.
[00:25:05] Under billing. So if you go to billing, we have only one screen here and this button.
[00:25:10] To the tag shield because we have only tag shield currently, right? In one web, so once we um
[00:25:15] Migrate tax relief clients, we might need to have separate tabs here for.
[00:25:20] Each of those services. So that's what we have in this mockup.
[00:25:25] payment section when we go to billing the same we the location is the same
[00:25:30] Under billing, we might have four different apps. The tax shield one is a
[00:25:35] Current existing screen. It will remain as it is, but we'll be adding a tax relief.
[00:25:40] A tax one for tax preparation and one for payments overdue. Payments overdue is something.
[00:25:45] That business wants to display any overdue payments either for tax relief or tax.
[00:25:50] anything due from the client, we might need to pull that in and display it here.
[00:25:55] And then tax relief is a migrated screen from client to.
[00:26:00] Let me go to client portal and show you this one, right?
[00:26:05] this screen the payments this is what we are migrating and putting this under the
[00:26:10] tab, tax relief, which shows all the payment history and payment.
[00:26:15] Method for investigation and resolution.
[00:26:20] Okay. Yeah. And tax relief existing, existing screen in one.
[00:26:25] web and tax preparation is something new we may
[00:26:30] Might need to add.
[00:26:35] And then the last portion is the enrollment channel. Now so there are three enrollments that will be happening.
[00:26:40] Currently, in client portal, one is for this investigation. When they enroll for investigation, they
[00:26:45] will do it in a tunnel which is displayed within client portal. Same with the resolution.
[00:26:50] And there is a third service called OTS360. All these three enrollment.
[00:26:55] tunnels need to be migrated to one web as well. So each of these tunnels has
[00:27:00] at least 15 to 20 pages which they migrate from one after another clicking next
[00:27:05] And sign wherever they need to, and then finish the tunnel. So that should be migrated to one way.
[00:27:10] When they log into the OneWAP homepage, it should be displayed there.
[00:27:15] Is spending for them to complete.
[00:27:20] It's a workflow, Prashant. Like, you know, each enrollment is a workflow with a bunch of pages.
[00:27:25] That is the longest effort, enrollment workflows.
[00:27:30] But initially, if you set up the home page as per the new structure,
[00:27:35] menus then you'll be familiar with that then it's easy to add the enrollments after
[00:27:40] Yeah, and no change with the current endolment terminal. It's all the same, we don't need to change.
[00:27:45] any logic just you know migrate that to uh one web one to one yeah
[00:27:50] Migration. Yeah. I think it looks like the only changes.
[00:27:55] The main first setting up the menu, rearranging the menu.
[00:28:00] Then after that logic, we are not changing anything only like some UI changes.
[00:28:05] That's all. Yeah, except for adding some additional tabs.
[00:28:10] Sorting it out, and then payments. We are adding additional tabs for different sets of clients.
[00:28:15] Yeah, again, that's a rearranging the UI only, right? Yeah, we're not.
[00:28:20] Adding any new business logic. I think majority of the once you have the rearrangement.
[00:28:25] done the existing services should support it which
[00:28:30] Which you need to migrate into C-sharp.
[00:28:35] Any questions so far?
[00:28:40] Prashant, you got a good idea. It looks good, yeah.
[00:28:45] So this will be recorded and I think she's already recorded.
[00:28:50] Once the meeting is over, I think Pranav is running late. He said he'll join.
[00:28:55] it line 45 we might be done by then but you can send him the recording for sure
[00:29:00] Prashant, you can connect with him later once you get good understanding of the project.
[00:29:05] and explain explain what they can do
[00:29:15] Giving you the account and connection to the code repository.
[00:29:20] Is the next step from my side? Do you want anything else?
[00:29:25] So from our side, have we started?
[00:29:30] started any actual development or still we are analyzing this.
[00:29:35] Which one? So new screens are adding new screens.
[00:29:40] And changes from our side, we started with some AI stuff or not it.
[00:29:45] I did not understand.
[00:29:50] using the AI now for the development of the US.
[00:29:55] it started yeah nobody's using yeah yeah very limited you know searching something you know
[00:30:00] As far, but directly integrating into the AI, we recently got clawed literally last week.
[00:30:05] I've been asking everybody to integrate into the developer environment. I think, you know, you have.
[00:30:10] Visual Studio, right? Use Visual Studio, right?
[00:30:15] So,
[00:30:20] Yeah, community edition, I can use the Visual Studio, but VS Code.
[00:30:25] Nowadays, we are using the VS Code. VS Code is a pro pilot, mostly. Yeah.
[00:30:30] code can integrate with cloud as well so we have both co-pilot and cloud subscription
[00:30:35] So I feel cloud is more efficient for technical, but you decide what you want to use.
[00:30:40] use. If you integrate with your VS Code, I think
[00:30:45] you might have already used it right so cloud gives you the vs code extension as well so
[00:30:50] We have a console within your studio at the bottom, VS Code bottom.
[00:30:55] You want to copy client portal, you know, use the AI, migrate it.
[00:31:00] and then make changes on the to reduce the effort.
[00:31:05] Yeah. So first step is menu on the left side.
[00:31:10] you're going to adjust on the top and only focus on the request center.
[00:31:15] Yeah, you'll create the UI, but you'll complete the functionality of the request center.
[00:31:20] Is that correct? That's what the focus reflects me. Yes, but hold up.
[00:31:25] documents from Request Center should be uh displayed in File Manager. So I don't know if it makes sense to
[00:31:30] Work both pathways, it's up to you, but yeah, okay, so.
[00:31:35] Maybe in all three tabs you just want to complete it, then you'll be done with that.
[00:31:40] So you'll be focusing only on the documents tab basically, right?
[00:31:45] One after rearranging the menu. Yeah. So we don't even need to create the
[00:31:50] tax relief at this point then only change or move the documents out of
[00:31:55] Tax shield and complete that pages. Right? Yeah.
[00:32:00] Okay. You got it right, Vrishant?
[00:32:05] Yeah, I got now good context of this at application.
[00:32:10] Application side, but from the tech side, I need to dig into means once.
[00:32:15] That applications are configured at my local, then I'm not there.
[00:32:20] Confidence on that. Yeah. Yeah. Mostly in migration projects, what we are doing, right?
[00:32:25] So whatever that legacy code, we vectorize that right before.
[00:32:30] Using any tool. So I will look into it, how we can do it, how much.
[00:32:35] Code volume. Right. Once that set up on my machine.
[00:32:40] So, I will get a good idea on that and prepare some plan from my.
[00:32:45] Side. Okay, sounds good. Yeah. So I'll
[00:32:50] I'll have my operations guy create an account for you and VPN access to you.
[00:32:55] And once that is confirmed, I'll have him give you access to the code repository.
[00:33:00] For both client portal and one web. In that way, you'll understand, then you can download.
[00:33:05] both the course while downloading if you want some help to for setup i'll have it our program
[00:33:10] I think Emily Wright and the client portal, she can help set you up.
[00:33:15] And the old one. And the new one manual, there's another programmer who can help you set up the new code as well.
[00:33:20] And that way you can start debugging both and understand the code.
[00:33:25] Once you have that set up, let me know what does it.
[00:33:30] Take, like, how long is it going to take? All that stuff, all that stuff.
[00:33:35] Sure. Yeah, so the traditionally they said the complete migration will
[00:33:40] Take nine months to 12 months, right? That's what they've been saying, right, Lakshmi? For all that.
[00:33:45] All the tabs, everything. Or all the only in the information request, what did they?
[00:33:50] Until May yeah two months may end two months so
[00:33:55] So that's what we had to cut down, Krishna, once you set up everything.
[00:34:00] Yeah, definitely I can give you the revised time.
[00:34:05] Timeline, yeah. Timeline is more critical.
[00:34:10] I have a
[00:34:15] A lot of questions, not for now, but once I got that quote, definitely.
[00:34:20] I can connect with Alakshimi or you.
[00:34:25] So Lakshmi, you are also handling technical stuff, right? Or how it is?
[00:34:30] Uh technical will be uh b how do uh you want to go uh with that uh bank cut should we
[00:34:35] I want to involve Van and Emily later.
[00:34:40] So but first he you know we'll give you all the connection setups everything.
[00:34:45] Then once he gets at least the basic thing set up, then we'll have Emily and Van.
[00:34:50] Take it over from there. Emily is the one who has been handling the client.
[00:34:55] Portal right now, Pashant. Okay. So she understands every detail of
[00:35:00] The world legacy application. So the new application.
[00:35:05] The person named Emmanuel, he's the one who did a lot of work.
[00:35:10] On that one, Van is the technical manager for these two leaders. So the solution architect.
[00:35:15] So I can connect with all three of them so that they can help you set up or
[00:35:20] Answer any questions you have. Then, you know.
[00:35:25] when when you are ready you should let me know but I can get you the VPN
[00:35:30] Connections this week, everything this week. So, whenever you're ready, I can connect with them.
[00:35:35] we can connect uh Emily with and you know Van Tu.
[00:35:40] with you. I can join that meeting as well. One or two more meetings.
[00:35:45] comfortable then you can directly connect with Lakshmi and Emily and then take it from there.
[00:35:50] Okay.
[00:35:55] So it's good.
[00:36:00] I'll stop the recording now.
